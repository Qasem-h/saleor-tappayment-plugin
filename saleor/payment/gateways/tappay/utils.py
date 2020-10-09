import json
import logging
from decimal import Decimal
from typing import Any, Callable, Dict, Optional

import tappayment as TapPay

from babel.numbers import get_currency_precision

from ....payment.models import Payment
from ... import PaymentError
from ...interface import PaymentData

logger = logging.getLogger(__name__)


FAILED_STATUSES = ["REFUSID", "ABANDONED", "CANCELLED","FAILED","DECLINED","RESTRICTED","UNKNOWN","TIMEDOUT","VOID"]
PENDING_STATUSES = ["INITIATED"]
AUTH_STATUS = "AUTHORIZED"

def get_amount_for_tappay(amount: Decimal) -> int:

    a =  Decimal(amount).quantize(Decimal('.000'))
    return int(a)

def call_api_clinet(request_data: Optional[Dict[str, Any]], method: Callable) -> TapPay.Client:
    try:
        return method(request_data)
    except (ValueError, TypeError) as e:
        logger.warning(f"Unable to process the payment: {e}")
        raise PaymentError("Unable to process the payment request.")


def init_data_for_payment(
    payment_information: "PaymentData",
    return_url: str,
    payment_source: str,
) -> Dict[str, Any]:
    payment_data = payment_information.data or {}

    if not payment_data.pop("is_valid", True):
        raise PaymentError("Payment data are not valid.")

    extra_request_params = {}
    if "browserInfo" in payment_data:
        extra_request_params["browserInfo"] = payment_data["browserInfo"]
    if "billingAddress" in payment_data:
        extra_request_params["billingAddress"] = payment_data["billingAddress"]

    request_data = {
        "amount": get_amount_for_tappay(payment_information.amount),
        "currency": payment_information.currency,
        "customer": {
               "email": payment_information.customer_email,
               "first_name": "first_name",

                },
        'source':    {"id": payment_source},
        'redirect':  {"url": return_url},
        'post':      {"url": return_url},
        **extra_request_params,
    }
    return request_data


def init_for_payment_refund(
    payment_information: "PaymentData", token
) -> Dict[str, Any]:
    return {
        "charge_id": payment_information.token,
        "currency": payment_information.currency,
        "amount": get_amount_for_tappay(payment_information.amount),
        "reason": "reason",
    }


def request_for_payment_authorize_capture(
    payment_information: "PaymentData", customer_id: str, token: str
) -> Dict[str, Any]:
    return {
        "currency": payment_information.currency,
        "amount": get_amount_for_tappay(payment_information.amount),
        "customer": {
            "id": customer_id,
        },
        "source": {
            "id": token,
        },
    }

def call_capture(
    payment_information: "PaymentData",
    token: str,
    tappay_client: TapPay.Client,
):
    authorize_id = token
    try:
        result = call_api_clinet(authorize_id, tappay_client.payment.get_authorize_status)
    except (ValueError, TypeError) as e:
        logger.warning(f"Unable to process the payment: {e}")
        raise PaymentError("Unable to process the payment request.")
    customer = result.get("customer")

    if "id" in customer:
        customer_id = customer.get("id")
    request = request_for_payment_authorize_capture(
        payment_information=payment_information,
        customer_id=customer_id,
        token=token,
    )
    return call_api_clinet(request, tappay_client.payment.authorize_capture)

def init_for_payment_void_or_cancel(
    payment_information: "PaymentData",  token: str,
):
    return {
        "authorize_id": token,
    }