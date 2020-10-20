import { storiesOf } from "@storybook/react";
import { action } from "@storybook/addon-actions";
import React from "react";
import { IntlProvider } from "react-intl";

import { TapPayPaymentGateway } from ".";

const processPayment = action("processPayment");
const submitPayment = async () => action("submitPayment");
const submitPaymentSuccess = action("submitPaymentSuccess");
const onError = action("onError");

storiesOf("@components/organisms/TapPayPaymentGateway", module)
  .addParameters({ component: TapPayPaymentGateway })
  .addDecorator(story => <IntlProvider locale="en">{story()}</IntlProvider>)
  .add("default", () => (
    <TapPayPaymentGateway
      processPayment={processPayment}
      submitPayment={submitPayment}
      submitPaymentSuccess={submitPaymentSuccess}
      onError={onError}
    />
  ));
