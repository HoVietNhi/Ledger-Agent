import os

import stripe


def main() -> None:
    api_key = os.getenv("STRIPE_SECRET_KEY", "").strip()

    if not api_key.startswith("sk_test_"):
        raise RuntimeError(
            "STRIPE_SECRET_KEY must be a Stripe TEST key."
        )

    stripe.api_key = api_key
    stripe.max_network_retries = 2

    # TEST payment method from Stripe's sandbox.
    payment_method = stripe.PaymentMethod.create(
        type="card",
        card={
            "token": "tok_visa",
        },
    )

    customer = stripe.Customer.create(
        name="Safe Signal Demo User",
        email="safesignal-demo@example.com",
        payment_method=payment_method.id,
        invoice_settings={
            "default_payment_method": payment_method.id,
        },
        metadata={
            "source": "safesignal_hackathon_demo",
        },
    )

    product = stripe.Product.create(
        name="StreamBox Pro",
        metadata={
            "source": "safesignal_hackathon_demo",
        },
    )

    price = stripe.Price.create(
        product=product.id,
        unit_amount=2999,
        currency="cad",
        recurring={
            "interval": "month",
        },
    )

    subscription = stripe.Subscription.create(
        customer=customer.id,
        items=[
            {
                "price": price.id,
            }
        ],
        metadata={
            "source": "safesignal_hackathon_demo",
            "provider_name": "StreamBox Pro",
        },
    )

    print("H3 Stripe demo subscription created")
    print("customer_id =", customer.id)
    print("product_id =", product.id)
    print("price_id =", price.id)
    print("subscription_id =", subscription.id)
    print("status =", subscription.status)
    print("cancel_at_period_end =", subscription.cancel_at_period_end)
    print("livemode =", subscription.livemode)


if __name__ == "__main__":
    main()