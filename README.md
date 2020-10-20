## Saleor Tap Payment Gateways Plugin
  [Tap Payment API Docs](https://tappayments.api-docs.io/)

## Getting Started

for install tap payment gateway follow this steps

### Prerequisites

- Saleor >= 2.10
- Tap Payment Clinet API Python Package  [Github](https://github.com/Qasem-h/tappayment-python)  |  [Pypi](https://pypi.org/project/TapPayment/)

## Installing

#### Install Tap Payment Python Package 
 In saleor root add `TapPayment==0.0.2` into  `requirements.txt`
 and run this command :
  ```
  python -m pip install -r requirements.txt
  ```

#### Install Tap Payment Plagin in saleor API

Clone the repository:
```
git clone git@github.com:Qasem-h/saleor-tappayment-plugin.git
```

Copy `saleor` folder in saleor API root

Edite saleor API `setting.py` and add this line:
```python
PLUGINS = [
     #...
     "saleor.payment.gateways.tappay.plugin.TapPayGatewayPlugin",
 ]
```

#### Configuration saleor-storefront

 Copy `saleor-storefront` folder saleor-storefront  root
