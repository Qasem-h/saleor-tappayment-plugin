import json
import logging
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlencode

import tappayment as TapPay

import graphene
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.core.handlers.wsgi import WSGIRequest
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseNotFound,
    QueryDict,
)
# from django.http.request import HttpHeaders
from django.shortcuts import redirect
from graphql_relay import from_global_id

from ....checkout.complete_checkout import complete_checkout
from ....checkout.models import Checkout
from ....core.transactions import transaction_with_commit_on_errors
from ....core.utils.url import prepare_url
from ....discount.utils import fetch_active_discounts
from ....order.actions import (
    cancel_order,
    order_authorized,
    order_captured,
    order_refunded,
)

from ....payment.models import Payment, Transaction
from ... import ChargeStatus, PaymentError, TransactionKind
from ...gateway import payment_refund_or_void
from ...interface import GatewayConfig, GatewayResponse
from ...utils import create_payment_information, create_transaction

from .utils import FAILED_STATUSES, call_api_clinet

logger = logging.getLogger(__name__)


def get_payment(
    payment_id: Optional[str], transaction_id: Optional[str] = None
) -> Optional[Payment]:
    transaction_id = transaction_id or ""
    if not payment_id:
        logger.warning("Missing payment ID. Reference %s", transaction_id)
        return None
    try:
        _type, db_payment_id = from_global_id(payment_id)
    except UnicodeDecodeError:
        logger.warning(
            "Unable to decode the payment ID %s. Reference %s",
            payment_id,
            transaction_id,
        )
        return None
    payment = (
        Payment.objects.prefetch_related("order", "checkout")
        .select_for_update(of=("self",))
        .filter(id=db_payment_id, is_active=True, gateway="tappayment.gosell")
        .first()
    )
    if not payment:
        logger.warning(
            "Payment for %s was not found. Reference %s", payment_id, transaction_id
        )
    return payment


def get_checkout(payment: Payment) -> Optional[Checkout]:
    if not payment.checkout:
        return None
    # Lock checkout in the same way as in checkoutComplete
    return (
        Checkout.objects.select_for_update(of=("self",))
        .prefetch_related("gift_cards", "lines__variant__product",)
        .select_related("shipping_method__shipping_zone")
        .filter(pk=payment.checkout.pk)
        .first()
    )


def create_order(payment, checkout):
    try:
        discounts = fetch_active_discounts()
        order, _, _ = complete_checkout(
            checkout=checkout,
            payment_data={},
            store_source=False,
            discounts=discounts,
            user=checkout.user or AnonymousUser(),
        )
    except ValidationError:
        payment_refund_or_void(payment)
        return None
    # Refresh the payment to assign the newly created order
    payment.refresh_from_db()
    return order


    

@transaction_with_commit_on_errors()
def handle_additional_actions(
    request: WSGIRequest, payment_details: Callable,
):
    payment_id =  request.GET.get("payment")
    checkout_pk = request.GET.get("checkout")
    authorize_id =      request.GET.get("tap_id")

    if not payment_id or not checkout_pk:
        return HttpResponseNotFound()

    payment = get_payment(payment_id, transaction_id=None)
    if not payment:
        return HttpResponseNotFound(
            "Cannot perform payment.There is no active tappay payment."
        )
    if not payment.checkout or str(payment.checkout.token) != checkout_pk:
        return HttpResponseNotFound(
            "Cannot perform payment.There is no checkout with this payment."
        )

   
    return_url = payment.return_url

    if not return_url:
        return HttpResponseNotFound(
            "Cannot perform payment. Lack of data about returnUrl."
        )

    try:
        request_data = prepare_api_request_data(authorize_id)
    except KeyError as e:

        return HttpResponseBadRequest(e.args[0])
    try:
        result = call_api_clinet(authorize_id, payment_details)
    except PaymentError as e:
        return HttpResponseBadRequest(str(e))

    handle_api_response(payment, result)

    redirect_url = prepare_redirect_url(payment_id, checkout_pk, result, return_url)
    return redirect(redirect_url)


def prepare_api_request_data(tap_id: str):
    if not tap_id:
        raise KeyError(
            "Cannot perform payment. Lack of payment data and parameters information."
        )

    api_request_data = {
        "authorize_id": tap_id,
    }

    return api_request_data


def prepare_redirect_url(
    payment_id: str, checkout_pk: str, api_response: TapPay.Client, return_url: str
):
    checkout_id = graphene.Node.to_global_id(
        "Checkout", checkout_pk  # type: ignore
    )

    params = {
        "checkout": checkout_id,
        "payment": payment_id,
        "status": api_response["status"],
    }

    # Check if further action is needed.
    if "action" in api_response:
        params.update(api_response["action"])

    return prepare_url(urlencode(params), return_url)


def handle_api_response(
    payment: Payment, response: TapPay.Client,
):
    checkout = get_checkout(payment)
    payment_data = create_payment_information(
        payment=payment, payment_token=payment.token
    )

    error = response.get("error")

    result_code = response["status"]
    is_success = result_code not in FAILED_STATUSES

    transactions = response.get("transaction")
    action_required = False
    if "url" in transactions:
        action_required = True

    gateway_response = GatewayResponse(
        is_success=is_success,
        action_required=action_required,
        kind=TransactionKind.ACTION_TO_CONFIRM,
        amount=payment_data.amount,
        currency=payment_data.currency,
        transaction_id=response.get("id", ""),
        error=error,
        raw_response=response,
        action_required_data=response.get("transaction"),
        searchable_key=response.get("id", ""),
    )

    create_transaction(
        payment=payment,
        kind=TransactionKind.ACTION_TO_CONFIRM,
        action_required=action_required,
        payment_information=payment_data,
        gateway_response=gateway_response,
    )

    if is_success and not action_required:
        create_order(payment, checkout)
