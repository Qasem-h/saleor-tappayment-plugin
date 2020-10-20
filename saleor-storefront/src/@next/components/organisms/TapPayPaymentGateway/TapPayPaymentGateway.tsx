import React, { useEffect, useRef, useState } from "react";

import { IFormError } from "@types";
import { CompleteCheckout_checkoutComplete_order } from "@saleor/sdk/lib/mutations/gqlTypes/CompleteCheckout";
import { ErrorMessage } from "@components/atoms";

export const tappayConfirmationStatus = ["AUTHORIZED", "CHARGED"];

interface TapPayError {
  error?: string;
}

export interface IProps {
  formRef?: React.RefObject<HTMLFormElement>;

  processPayment: () => void;

  submitPayment: () => Promise<any>;

  submitPaymentSuccess: (
    order?: CompleteCheckout_checkoutComplete_order
  ) => void;

  errors?: IFormError[];

  onError: (errors: IFormError[]) => void;
}

const TapPayPaymentGateway: React.FC<IProps> = ({
  formRef,
  processPayment,
  submitPayment,
  submitPaymentSuccess,
  errors,
  onError
}: IProps) => {
  const gatewayRef = useRef<HTMLDivElement>(null);

  const handlePaymentAction = (data?: paymentActionData) => {
    if (data?.url) {
      window.location.href = data?.url;
    } else {
      onError([new Error("Invalid payment url. please try again")]);
    }
  };

  const onSubmitTapPayForm = async () => {
    const payment = await submitPayment();
    if (payment.errors?.length) {
      onError(payment.errors);
    } else {
      let paymentActionData;
      try {
        paymentActionData = JSON.parse(payment.confirmationData);
      } catch (parseError) {
        onError([
          new Error(
            "Payment needs confirmation but data required for confirmation received from the server is malformed."
          )
        ]);
      }
      try {
        handlePaymentAction(paymentActionData);
      } catch (error) {
        onError([new Error(error)]);
      }
    }
  };

  const onTapPayError = (error?: TapPayError) => {
    if (error?.error) {
      onError([{ message: error.error }]);
    } else {
      onError([new Error("error in tappay")]);
    }
  };
  useEffect(() => {
    (formRef?.current as any)?.addEventListener("submitComplete", () => {
      onSubmitTapPayForm();
    });
  }, [formRef]);

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    processPayment();
  };

  return (
    <form ref={formRef} onSubmit={handleSubmit}>
      <div ref={gatewayRef} />
      <ErrorMessage errors={errors} />
    </form>
  );
};

export { TapPayPaymentGateway };
