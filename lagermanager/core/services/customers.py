"""
Keeping every address attached to a customer.

A document is billed to a customer, and a balance is kept per customer, so an
address that a document can be sent to must always have one.  The Wiffzack sync
guarantees this for imported addresses; this module provides the same guarantee
for addresses created through the API and for the one-off backfill of rows that
predate the customer model.
"""
from core.models import Address, Customer
from core.services.numbering import allocate_customer_number, allocate_customer_numbers


def _customer_kwargs(address: Address) -> dict[str, str]:
    """Seed a customer from the address it is created for.

    Address's contact fields are legacy nullable columns, so None and '' both
    have to collapse to ''.
    """
    return {
        'name': address.display_name,
        'email': address.email or '',
        'telefon': address.telefon or '',
        'uid': address.uid or '',
    }


def _link(address: Address, customer: Customer) -> Customer:
    address.customer = customer
    address.save(update_fields=['customer'])
    customer.default_address = address
    customer.save(update_fields=['default_address'])
    return customer


def ensure_customer_for_address(address: Address) -> Customer:
    """Return the address's customer, creating a 1:1 one if it has none.

    Caller is responsible for the surrounding transaction.
    """
    if address.customer_id is not None and address.customer is not None:
        return address.customer
    customer = Customer.objects.create(
        customer_number=allocate_customer_number(),
        **_customer_kwargs(address),
    )
    return _link(address, customer)


def ensure_customers_for_addresses(addresses: list[Address]) -> int:
    """ensure_customer_for_address for many addresses, with one number bump.

    Allocating the numbers in a single locked bump matters for the initial
    backfill, which can walk thousands of addresses.  Returns how many customers
    were created.
    """
    orphans = [a for a in addresses if a.customer_id is None]
    if not orphans:
        return 0
    numbers = allocate_customer_numbers(len(orphans))
    for address, number in zip(orphans, numbers, strict=True):
        _link(address, Customer.objects.create(
            customer_number=number, **_customer_kwargs(address)))
    return len(orphans)
