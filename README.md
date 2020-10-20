# Saleor Tap Payment Gateways Plugin
  [Tap Payment API Docs](https://tappayments.api-docs.io/)

## Getting Started

for install tap payment gateway follow this steps

### Prerequisites

- Saleor =>2.10
- Tappayment Clinet API Python Package 
  [Tap Payment Clinet Package Github](https://github.com/Qasem-h/tappayment-python)
  [Tap Payment Clinet Package Pypi](https://pypi.org/project/)
  ```  
   pip install tappayment
  ```
   

### Installing

Clone the repository:

```
git clone https://github.com/Qasem-h/tappayment-python.git
```

Copy in saleor API root

copy it in saleor root directory
 
Edite saleor API `setting.py`:
```python
PLUGINS = [
     #...
     "saleor.payment.gateways.tappay.plugin.TapPayGatewayPlugin",
 ]
```