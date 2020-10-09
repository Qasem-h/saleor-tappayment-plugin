# External Apps
import json
from typing import List, Optional
from urllib.parse import urlencode

import tappayment as TapPay

# Dejango Apps
from django.core.exceptions import ObjectDoesNotExist
from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse, HttpResponseNotFound

# Saleor Apps
from ....checkout.models import Checkout
from ....core.utils import build_absolute_uri
from ....core.utils.url import prepare_url
from ....plugins.base_plugin import BasePlugin, ConfigurationTypeField
from ... import PaymentError, TransactionKind
from ...interface import GatewayConfig, GatewayResponse, PaymentData, PaymentGateway
from ...models import Payment, Transaction
from ..utils import get_supported_currencies


# Plugin App
from .utils import (
    AUTH_STATUS,
    FAILED_STATUSES,
    PENDING_STATUSES,
    call_api_clinet,
    call_capture,
    init_data_for_payment,
    init_for_payment_void_or_cancel,
    init_for_payment_refund,
)
from .webhooks import handle_additional_actions




GATEWAY_NAME = "Tappay"
ADDITIONAL_ACTION_PATH = "/additional-actions"


def require_active_plugin(fn):
    def wrapped(self, *args, **kwargs):
        previous = kwargs.get("previous_value", None)
        if not self.active:
            return previous
        return fn(self, *args, **kwargs)

    return wrapped


class TapPayGatewayPlugin(BasePlugin):
    PLUGIN_ID = "tappayment.gosell"
    PLUGIN_NAME = GATEWAY_NAME
    DEFAULT_CONFIGURATION = [
        {"name": "api-key", "value": None},
        {"name": "supported-currencies", "value": ""},
        {"name": "source-id", "value": ""},
        {"name": "auto-capture", "value": False},
    ]

    CONFIG_STRUCTURE = {
        "api-key": {
            "type": ConfigurationTypeField.SECRET,
            "help_text": "Provide TapPayment secret API key.",
            "label": "Secret API key",
        },
        "supported-currencies": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Determines currencies supported by gateway."
                " Please enter currency codes separated by a comma.",
                "label": "Supported currencies",
        },
        "source-id": {
            "type": ConfigurationTypeField.STRING,
            "help_text": (
                "src_all -> to display all payment methods on Tap Payment page"
                "src_card -> to display only the card collection payment methods"
            ),
            "label": "Paymeny Source ID",
        },
        "auto-capture": {
            "type": ConfigurationTypeField.BOOLEAN,
            "help_text": (
                "If enabled, Saleor will automatically capture funds. If, disabled, the"
                " funds are blocked but need to be captured manually."
            ),
            "label": "Automatically capture funds when a payment is made",
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configuration = {item["name"]: item["value"] for item in self.configuration}
        self.config = GatewayConfig(
            gateway_name=GATEWAY_NAME,
            auto_capture=configuration["auto-capture"],
            supported_currencies=configuration["supported-currencies"],
            connection_params={
                "api-key": configuration["api-key"],
                "source-id": configuration["source-id"],
            },
        )
        api_key = self.config.connection_params["api-key"]
        self.tappay = TapPay.Client(
            api_token=api_key
        )

    def webhook(self, request: WSGIRequest, path: str, previous_value) -> HttpResponse:
        config = self._get_gateway_config()
        if path.startswith(ADDITIONAL_ACTION_PATH):
            return handle_additional_actions(
                request, self.tappay.payment.get_authorize_status,
            )
        return HttpResponseNotFound()

    def _get_gateway_config(self) -> GatewayConfig:
        return self.config

    @require_active_plugin
    def token_is_required_as_payment_input(self, previous_value):
        return False

    @require_active_plugin
    def get_payment_gateway_for_checkout(
        self, checkout: "Checkout", previous_value,
    ) -> Optional["PaymentGateway"]:
        config = self._get_gateway_config()
        return PaymentGateway(
            id=self.PLUGIN_ID,
            name=self.PLUGIN_NAME,
            config=[
                {"field": "config", "value": checkout},
            ],
            currencies=self.get_supported_currencies([]),
        )

    @require_active_plugin
    def process_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        try:
            payment = Payment.objects.get(pk=payment_information.payment_id)
        except ObjectDoesNotExist:
            raise PaymentError("Payment cannot be performed. Payment does not exists.")

        checkout = payment.checkout
        if checkout is None:
            raise PaymentError(
                "Payment cannot be performed. Checkout for this payment does not exist."
            )

        params = urlencode(
            {"payment": payment_information.graphql_payment_id, "checkout": checkout.pk}
        )
        return_url = prepare_url(
            params,
            build_absolute_uri(
                f"/plugins/{self.PLUGIN_ID}/additional-actions"
            ),  # type: ignore
        )
        request_data = init_data_for_payment(
            payment_information,
            return_url=return_url,
            payment_source=self.config.connection_params["source-id"],

        )

        result = call_api_clinet(request_data, self.tappay.payment.authorize)
        result_code = result.get("status")
        error = result.get("error")
        is_success = result_code not in FAILED_STATUSES
        kind = TransactionKind.AUTH
        if result_code in PENDING_STATUSES:
            kind = TransactionKind.PENDING
        elif adyen_auto_capture:
            kind = TransactionKind.CAPTURE

        if result_code in PENDING_STATUSES:
            pass
        # If auto capture is enabled, let's make a capture the auth payment
        elif self.config.auto_capture and result_code == AUTH_STATUS :
            kind = TransactionKind.CAPTURE
            token = result.get("id")
            result = call_capture(
                payment_information=payment_information,
                token=token,
                tappay_client= self.tappay,
            )

        return GatewayResponse(
            is_success=is_success,
            action_required="transaction" in result,
            kind=kind,
            amount=payment_information.amount,
            currency=payment_information.currency,
            transaction_id=result.get("id", ""),
            error=error,
            raw_response=result,
            action_required_data=result.get("transaction"),
            searchable_key=result.get("id", ""),
        )

    @require_active_plugin
    def get_payment_config(self, previous_value):
        return []

    @require_active_plugin
    def get_supported_currencies(self, previous_value):
        config = self._get_gateway_config()
        return get_supported_currencies(config, GATEWAY_NAME)

    def _process_additional_action(self, payment_information: "PaymentData", kind: str):
        config = self._get_gateway_config()
        additional_data = payment_information.data
        if not additional_data:
            raise PaymentError("Unable to finish the payment.")

        result = call_api_clinet(additional_data, self.tappay.payment.authorize)
        result_code = result['status']
        is_success = result_code not in FAILED_STATUSES

        if result_code in PENDING_STATUSES:
            kind = TransactionKind.PENDING
        elif is_success and config.auto_capture:
            # For enabled auto_capture on Saleor side we need to proceed an additional
            # action
            response = self.capture_payment(payment_information, None)
            is_success = response.is_success

        return GatewayResponse(
            is_success=is_success,
            action_required=True,
            kind=kind,
            amount=payment_information.amount,
            currency=payment_information.currency,
            transaction_id=result.get("id", ""),
            error=result.get("error",""),
            raw_response=result,
            searchable_key=result.get("id", ""),
        )

    @require_active_plugin
    def confirm_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        print("confirm_payment")
        config = self._get_gateway_config()
        # The additional checks are proceed asynchronously so we try to confirm that
        # the payment is already processed
        payment = Payment.objects.filter(id=payment_information.payment_id).first()
        if not payment:
            raise PaymentError("Unable to find the payment.")

        transaction = (
            payment.transactions.filter(
                kind=TransactionKind.ACTION_TO_CONFIRM,
                is_success=True,
                action_required=False,
            )
            .exclude(token__isnull=False, token__exact="")
            .last()
        )

        # tappay_auto_capture = self.config.connection_params["tappay_auto_capture"]
        kind = TransactionKind.AUTH
        if config.auto_capture:
            kind = TransactionKind.CAPTURE

        if not transaction:

            return self._process_additional_action(payment_information, kind)

        result_code = transaction.gateway_response.get("status", "")
        if result_code in PENDING_STATUSES:
            kind = TransactionKind.PENDING

        # We already have the ACTION_TO_CONFIRM transaction, it means that
        # payment was processed asynchronous and no additional action is required

        # Check if we didn't process this transaction asynchronously
        transaction_already_processed = payment.transactions.filter(
            kind=kind,
            is_success=True,
            action_required=False,
            amount=payment_information.amount,
            currency=payment_information.currency,
        ).first()
        is_success = True

        # confirm that we should proceed the capture action
        if (
            not transaction_already_processed
            and config.auto_capture
            and kind == TransactionKind.CAPTURE
        ):
            response = self.capture_payment(payment_information, None)
            is_success = response.is_success

        token = transaction.token
        if transaction_already_processed:
            token = transaction_already_processed.token

        return GatewayResponse(
            is_success=is_success,
            action_required=True,
            kind=kind,
            amount=payment_information.amount,  # type: ignore
            currency=payment_information.currency,  # type: ignore
            transaction_id=token,  # type: ignore
            error=None,
            raw_response={},
            transaction_already_processed=bool(transaction_already_processed),
        )

    @require_active_plugin
    def refund_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        # we take Auth kind because it contains the transaction id that we need
        print("refund_payment")
        transaction = (
            Transaction.objects.filter(
                payment__id=payment_information.payment_id,
                kind=TransactionKind.AUTH,
                is_success=True,
            )
            .exclude(token__isnull=False, token__exact="")
            .last()
        )

        if not transaction:
            # If we don't find the Auth kind we will try to get Capture kind
            transaction = (
                Transaction.objects.filter(
                    payment__id=payment_information.payment_id,
                    kind=TransactionKind.CAPTURE,
                    is_success=True,
                )
                .exclude(token__isnull=False, token__exact="")
                .last()
            )

        if not transaction:
            raise PaymentError("Cannot find a payment reference to refund.")

        request = init_for_payment_refund(
            payment_information=payment_information,
            token=transaction.token,
        )
        result = call_api_clinet(request, self.tappay.payment.refund)

        return GatewayResponse(
            is_success=True,
            action_required=False,
            kind=TransactionKind.REFUND_ONGOING,
            amount=payment_information.amount,
            currency=payment_information.currency,
            transaction_id=result.get("id", ""),
            error="",
            raw_response=result,
            searchable_key=result.get("id", ""),
        )

    @require_active_plugin
    def capture_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        print("capture_payment")
        if not payment_information.token:
            raise PaymentError("Cannot find a payment reference to capture.")

        result = call_capture(
            payment_information=payment_information,
            token=payment_information.token,
            tappay_client=self.tappay,
        )
   
        return GatewayResponse(
            is_success=True,
            action_required=False,
            kind=TransactionKind.CAPTURE,
            amount=payment_information.amount,
            currency=payment_information.currency,
            transaction_id=result.get("id", ""),
            error="",
            raw_response=result,
            searchable_key=result.get("id", ""),
        )

    @require_active_plugin
    def void_payment(
        self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        print("void_payment")
        request = init_for_payment_void_or_cancel(
            payment_information=payment_information,
            token=payment_information.token,  # type: ignore
        )
        result = call_api_clinet(request, self.tappay.payment.authorize_void)

        return GatewayResponse(
            is_success=True,
            action_required=False,
            kind=TransactionKind.VOID,
            amount=payment_information.amount,
            currency=payment_information.currency,
            transaction_id=result.get("id", ""),
            error="",
            raw_response=result,
            searchable_key=result.get("id", ""),
        )