"""Tests for the Customer model, its number sequence, and the address link."""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APITestCase

from core.models import Address, Customer, CustomerNumberSequence
from core.services.customers import (
    ensure_customer_for_address,
    ensure_customers_for_addresses,
)
from core.services.numbering import (
    CUSTOMER_NUMBER_PREFIX,
    allocate_customer_number,
    allocate_customer_numbers,
)


class AllocateCustomerNumberTests(TestCase):
    def test_numbers_start_at_one_and_are_zero_padded(self) -> None:
        self.assertEqual(allocate_customer_number(), 'K0001')
        self.assertEqual(allocate_customer_number(), 'K0002')

    def test_bulk_allocation_is_consecutive(self) -> None:
        self.assertEqual(allocate_customer_numbers(3), ['K0001', 'K0002', 'K0003'])
        self.assertEqual(allocate_customer_number(), 'K0004')

    def test_bulk_allocation_takes_one_bump(self) -> None:
        allocate_customer_numbers(5)
        seq = CustomerNumberSequence.objects.get(pk=1)
        self.assertEqual(seq.last_value, 5)

    def test_zero_or_negative_count_allocates_nothing(self) -> None:
        self.assertEqual(allocate_customer_numbers(0), [])
        self.assertEqual(allocate_customer_numbers(-1), [])
        self.assertFalse(CustomerNumberSequence.objects.exists())

    def test_widens_past_9999(self) -> None:
        CustomerNumberSequence.objects.create(pk=1, last_value=9999)
        self.assertEqual(allocate_customer_number(), 'K10000')

    def test_the_prefix_is_configurable_in_one_place(self) -> None:
        self.assertTrue(
            allocate_customer_number().startswith(CUSTOMER_NUMBER_PREFIX))


class EnsureCustomerTests(TestCase):
    def test_creates_a_customer_and_links_it_both_ways(self) -> None:
        address = Address.objects.create(
            vorname='Max', nachname='Mustermann', email='max@example.com')
        customer = ensure_customer_for_address(address)

        address.refresh_from_db()
        self.assertEqual(address.customer, customer)
        self.assertEqual(customer.default_address, address)
        self.assertEqual(customer.name, 'Max Mustermann')
        self.assertEqual(customer.email, 'max@example.com')
        self.assertTrue(customer.customer_number.startswith('K'))

    def test_a_nameless_address_names_the_customer_after_its_street(self) -> None:
        """"Adresse #120" as a customer name tells nobody anything."""
        address = Address.objects.create(
            strasse='Papiermühlgasse 18/2/4', plz='8020', ort='Graz')
        customer = ensure_customer_for_address(address)
        self.assertEqual(customer.name, 'Papiermühlgasse 18/2/4, 8020 Graz')

    def test_a_named_address_does_not_drag_its_street_into_the_name(self) -> None:
        address = Address.objects.create(
            firma='Muster GmbH', strasse='Hauptstr. 1', plz='1010', ort='Wien')
        customer = ensure_customer_for_address(address)
        self.assertEqual(customer.name, 'Muster GmbH')

    def test_an_empty_address_still_falls_back_to_the_placeholder(self) -> None:
        address = Address.objects.create()
        customer = ensure_customer_for_address(address)
        self.assertEqual(customer.name, f'Adresse #{address.pk}')

    def test_bulk_creation_names_the_same_way(self) -> None:
        nameless = Address.objects.create(strasse='Hauptstr. 1', plz='1010', ort='Wien')
        named = Address.objects.create(firma='Muster GmbH')
        ensure_customers_for_addresses([nameless, named])

        nameless.refresh_from_db()
        named.refresh_from_db()
        self.assertEqual(nameless.customer.name, 'Hauptstr. 1, 1010 Wien')
        self.assertEqual(named.customer.name, 'Muster GmbH')

    def test_is_idempotent(self) -> None:
        address = Address.objects.create(vorname='Max', nachname='Mustermann')
        first = ensure_customer_for_address(address)
        second = ensure_customer_for_address(address)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Customer.objects.count(), 1)

    def test_null_contact_fields_become_empty_strings(self) -> None:
        """Address contact fields are legacy nullable columns."""
        address = Address.objects.create(firma='Test GmbH')
        customer = ensure_customer_for_address(address)
        self.assertEqual(customer.email, '')
        self.assertEqual(customer.telefon, '')
        self.assertEqual(customer.uid, '')

    def test_bulk_skips_addresses_that_already_have_one(self) -> None:
        linked = Address.objects.create(vorname='A', nachname='A')
        ensure_customer_for_address(linked)
        orphan = Address.objects.create(vorname='B', nachname='B')

        created = ensure_customers_for_addresses([linked, orphan])
        self.assertEqual(created, 1)
        self.assertEqual(Customer.objects.count(), 2)

    def test_bulk_on_empty_input_allocates_nothing(self) -> None:
        self.assertEqual(ensure_customers_for_addresses([]), 0)


class CustomerPropertyTests(TestCase):
    def test_str_includes_the_number(self) -> None:
        customer = Customer(customer_number='K0007', name='Mustermann GmbH')
        self.assertEqual(str(customer), 'K0007 – Mustermann GmbH')

    def test_str_without_a_number(self) -> None:
        self.assertEqual(str(Customer(name='Mustermann GmbH')), 'Mustermann GmbH')

    def test_display_name_falls_back_to_the_default_address(self) -> None:
        address = Address.objects.create(firma='Test GmbH')
        customer = Customer.objects.create(name='', default_address=address)
        self.assertEqual(customer.display_name, 'Test GmbH')

    def test_display_name_falls_back_to_a_nameless_addresss_street(self) -> None:
        address = Address.objects.create(strasse='Hauptstr. 1', plz='1010', ort='Wien')
        customer = Customer.objects.create(name='', default_address=address)
        self.assertEqual(customer.display_name, 'Hauptstr. 1, 1010 Wien')

    def test_billing_email_prefers_the_customers_own(self) -> None:
        address = Address.objects.create(firma='Test GmbH', email='addr@example.com')
        customer = Customer.objects.create(
            name='Test GmbH', email='own@example.com', default_address=address)
        self.assertEqual(customer.billing_email, 'own@example.com')

    def test_billing_email_falls_back_to_the_address(self) -> None:
        address = Address.objects.create(firma='Test GmbH', email='addr@example.com')
        customer = Customer.objects.create(name='Test GmbH', default_address=address)
        self.assertEqual(customer.billing_email, 'addr@example.com')

    def test_billing_email_is_empty_when_the_address_has_none(self) -> None:
        """Address.email is nullable; None must not leak out as a string."""
        address = Address.objects.create(firma='Test GmbH')
        customer = Customer.objects.create(name='Test GmbH', default_address=address)
        self.assertEqual(customer.billing_email, '')

    def test_billing_email_without_a_default_address(self) -> None:
        self.assertEqual(Customer.objects.create(name='X').billing_email, '')


class CustomerApiTests(APITestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_superuser('test', 'test@example.com', 'password')
        self.client.force_authenticate(user=self.user)

    def test_creating_a_customer_assigns_a_number(self) -> None:
        resp = self.client.post('/api/customers/', {'name': 'Mustermann GmbH'})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['customer_number'], 'K0001')
        self.assertEqual(resp.json()['balance'], '0.00')

    def test_creating_an_address_auto_creates_a_customer(self) -> None:
        resp = self.client.post('/api/addresses/', {
            'vorname': 'Max', 'nachname': 'Mustermann',
        })
        self.assertEqual(resp.status_code, 201)
        address = Address.objects.get(pk=resp.json()['id'])
        self.assertIsNotNone(address.customer)
        self.assertEqual(address.customer.default_address, address)

    def test_creating_an_address_for_an_existing_customer_keeps_it(self) -> None:
        first = Address.objects.create(vorname='Max', nachname='Mustermann')
        customer = ensure_customer_for_address(first)

        resp = self.client.post('/api/addresses/', {
            'customer': customer.pk, 'strasse': 'Zweitadresse 1',
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Customer.objects.count(), 1)
        # The second address does not steal the default.
        customer.refresh_from_db()
        self.assertEqual(customer.default_address, first)

    def test_default_address_must_belong_to_the_customer(self) -> None:
        customer = Customer.objects.create(name='A', customer_number='K0001')
        foreign = Address.objects.create(vorname='Fremd', nachname='Adresse')
        resp = self.client.patch(
            f'/api/customers/{customer.pk}/', {'default_address': foreign.pk})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('default_address', resp.json())

    def test_balance_endpoint(self) -> None:
        address = Address.objects.create(vorname='Max', nachname='Mustermann')
        customer = ensure_customer_for_address(address)
        resp = self.client.get(f'/api/customers/{customer.pk}/balance/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'balance': '0.00', 'available_credit': '0.00'})

    def test_ledger_endpoint_is_empty_for_a_new_customer(self) -> None:
        address = Address.objects.create(vorname='Max', nachname='Mustermann')
        customer = ensure_customer_for_address(address)
        resp = self.client.get(f'/api/customers/{customer.pk}/ledger/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'balance': '0.00', 'entries': []})

    def _search(self, q: str) -> list[tuple[str, str]]:
        results = self.client.get(f'/api/customers/?q={q}').json()['results']
        return [(r['customer_number'], r['name']) for r in results]

    def test_search_by_name_and_number(self) -> None:
        first = self.client.post('/api/customers/', {'name': 'Mustermann GmbH'}).json()
        second = self.client.post('/api/customers/', {'name': 'Andere AG'}).json()

        self.assertEqual(
            self._search('Mustermann'),
            [(first['customer_number'], 'Mustermann GmbH')])
        # Spells out which customer that number belongs to — the point of the
        # customer_number branch of the q filter.
        self.assertEqual(
            self._search(second['customer_number']),
            [(second['customer_number'], 'Andere AG')])
        self.assertEqual(self._search('ZZZ'), [])

    def test_requires_auth(self) -> None:
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get('/api/customers/').status_code, 401)


class CustomerLedgerEndpointTests(APITestCase):
    """The ledger endpoint reports a running balance and the acting user."""

    def setUp(self) -> None:
        self.user = User.objects.create_superuser('test', 'test@example.com', 'password')
        self.client.force_authenticate(user=self.user)
        address = Address.objects.create(vorname='Max', nachname='Mustermann')
        self.customer = ensure_customer_for_address(address)

    def test_running_balance(self) -> None:
        from billing.models import CustomerLedgerEntry

        CustomerLedgerEntry.objects.create(
            customer=self.customer,
            entry_type=CustomerLedgerEntry.EntryType.INVOICE,
            entry_date=datetime.date(2026, 6, 15),
            amount=Decimal('-120.00'),
            description='Rechnung RE1',
        )
        CustomerLedgerEntry.objects.create(
            customer=self.customer,
            entry_type=CustomerLedgerEntry.EntryType.PAYMENT,
            entry_date=datetime.date(2026, 7, 1),
            amount=Decimal('50.00'),
            description='Zahlung',
        )
        resp = self.client.get(f'/api/customers/{self.customer.pk}/ledger/')
        data = resp.json()
        self.assertEqual(data['balance'], '-70.00')
        self.assertEqual(
            [e['running_balance'] for e in data['entries']], ['-120.00', '-70.00'])
        self.assertEqual(data['entries'][0]['entry_type_display'], 'Rechnung')


class CustomerLedgerOrderingTests(APITestCase):
    """Ordered by content, not by insertion.

    The backfill wrote historic rows newest-first, so primary-key order put a
    Storno above the invoice it reverses and made the running balance read
    backwards.
    """

    def setUp(self) -> None:
        self.user = User.objects.create_superuser('test', 'test@example.com', 'password')
        self.client.force_authenticate(user=self.user)
        address = Address.objects.create(vorname='Max', nachname='Mustermann')
        self.customer = ensure_customer_for_address(address)
        self.date = datetime.date(2026, 6, 23)

    def _invoice(self, number: str):
        from billing.models import Invoice
        return Invoice.objects.create(
            customer=self.customer,
            address=self.customer.default_address,
            number=number,
            document_date=self.date,
            due_date=self.date,
            status=Invoice.Status.ISSUED,
        )

    def _entry(self, entry_type: str, amount: str, *, invoice=None, date=None):
        from billing.models import CustomerLedgerEntry
        return CustomerLedgerEntry.objects.create(
            customer=self.customer,
            entry_type=entry_type,
            entry_date=date or self.date,
            amount=Decimal(amount),
            description=f'{entry_type} {invoice.number if invoice else ""}'.strip(),
            invoice=invoice,
        )

    def _descriptions(self) -> list[str]:
        resp = self.client.get(f'/api/customers/{self.customer.pk}/ledger/')
        return [e['description'] for e in resp.json()['entries']]

    def test_a_storno_sits_under_the_invoice_it_reverses(self) -> None:
        from billing.models import CustomerLedgerEntry

        # Created newest-first, the way the backfill did it.
        third = self._invoice('PG260613')
        storno = self._invoice('PG260612')
        original = self._invoice('PG260610')
        self._entry(CustomerLedgerEntry.EntryType.INVOICE, '-60.00', invoice=third)
        self._entry(CustomerLedgerEntry.EntryType.INVOICE, '120.00', invoice=storno)
        self._entry(CustomerLedgerEntry.EntryType.INVOICE, '-120.00', invoice=original)

        self.assertEqual(self._descriptions(), [
            'invoice PG260610', 'invoice PG260612', 'invoice PG260613',
        ])

    def test_running_balance_follows_the_display_order(self) -> None:
        from billing.models import CustomerLedgerEntry

        storno = self._invoice('PG260612')
        original = self._invoice('PG260610')
        self._entry(CustomerLedgerEntry.EntryType.INVOICE, '120.00', invoice=storno)
        self._entry(CustomerLedgerEntry.EntryType.INVOICE, '-120.00', invoice=original)

        resp = self.client.get(f'/api/customers/{self.customer.pk}/ledger/')
        data = resp.json()
        self.assertEqual(
            [e['running_balance'] for e in data['entries']], ['-120.00', '0.00'])
        self.assertEqual(data['balance'], '0.00')

    def test_a_charge_comes_before_the_payment_that_settles_it(self) -> None:
        from billing.models import CustomerLedgerEntry

        invoice = self._invoice('PG260610')
        # Payment booked first, same date and same invoice.
        self._entry(CustomerLedgerEntry.EntryType.PAYMENT, '120.00', invoice=invoice)
        self._entry(CustomerLedgerEntry.EntryType.INVOICE, '-120.00', invoice=invoice)
        self._entry(CustomerLedgerEntry.EntryType.REMINDER_FEE, '-12.00', invoice=invoice)

        self.assertEqual(self._descriptions(), [
            'invoice PG260610', 'reminder_fee PG260610', 'payment PG260610',
        ])

    def test_entries_without_an_invoice_come_last_within_the_day(self) -> None:
        from billing.models import CustomerLedgerEntry

        self._entry(CustomerLedgerEntry.EntryType.PAYMENT, '50.00')
        invoice = self._invoice('PG260610')
        self._entry(CustomerLedgerEntry.EntryType.INVOICE, '-120.00', invoice=invoice)

        self.assertEqual(self._descriptions(), ['invoice PG260610', 'payment'])

    def test_date_still_wins_over_everything(self) -> None:
        from billing.models import CustomerLedgerEntry

        later = self._invoice('PG260601')
        earlier = self._invoice('PG260699')
        self._entry(CustomerLedgerEntry.EntryType.INVOICE, '-10.00',
                    invoice=later, date=datetime.date(2026, 7, 1))
        self._entry(CustomerLedgerEntry.EntryType.INVOICE, '-20.00',
                    invoice=earlier, date=datetime.date(2026, 6, 1))

        self.assertEqual(self._descriptions(),
                         ['invoice PG260699', 'invoice PG260601'])


class CustomerDeleteTests(APITestCase):
    """PROTECT FKs would otherwise surface as a 500."""

    def setUp(self) -> None:
        self.user = User.objects.create_superuser('test', 'test@example.com', 'password')
        self.client.force_authenticate(user=self.user)
        address = Address.objects.create(vorname='Max', nachname='Mustermann')
        self.customer = ensure_customer_for_address(address)

    def test_an_unused_customer_can_be_deleted(self) -> None:
        resp = self.client.delete(f'/api/customers/{self.customer.pk}/')
        self.assertEqual(resp.status_code, 204)

    def test_a_customer_with_an_invoice_is_refused(self) -> None:
        from billing.models import Invoice

        Invoice.objects.create(
            customer=self.customer,
            address=self.customer.default_address,
            document_date=datetime.date(2026, 6, 15),
            due_date=datetime.date(2026, 6, 29),
        )
        resp = self.client.delete(f'/api/customers/{self.customer.pk}/')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Rechnungen', resp.json()['detail'])

    def test_a_customer_with_a_payment_is_refused(self) -> None:
        from billing.models import Payment

        Payment.objects.create(
            customer=self.customer,
            payment_date=datetime.date(2026, 6, 15),
            amount=Decimal('50.00'),
        )
        resp = self.client.delete(f'/api/customers/{self.customer.pk}/')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Zahlungen', resp.json()['detail'])


class AddressPostalLabelTests(TestCase):
    """postal_label is what distinguishes one customer's addresses in a picker."""

    def test_street_only_address_falls_back_to_the_postal_address(self) -> None:
        address = Address.objects.create(
            strasse='Papiermühlgasse 18/2/4', plz='8020', ort='Graz')
        # No name, so both labels resolve to the postal address — never the
        # opaque "Adresse #<pk>", which also reaches e-mails and invoice lists.
        self.assertEqual(address.display_name, 'Papiermühlgasse 18/2/4, 8020 Graz')
        self.assertEqual(address.postal_label, 'Papiermühlgasse 18/2/4, 8020 Graz')
        self.assertEqual(str(address), 'Papiermühlgasse 18/2/4, 8020 Graz')

    def test_named_address_keeps_its_name_in_front(self) -> None:
        address = Address.objects.create(
            firma='Muster GmbH', strasse='Hauptstr. 1', plz='1010', ort='Wien')
        self.assertEqual(
            address.postal_label, 'Muster GmbH, Hauptstr. 1, 1010 Wien')

    def test_name_without_a_street_falls_back_to_the_name(self) -> None:
        address = Address.objects.create(vorname='Max', nachname='Mustermann')
        self.assertEqual(address.postal_label, 'Max Mustermann')

    def test_empty_address_falls_back_to_the_placeholder(self) -> None:
        address = Address.objects.create()
        self.assertEqual(address.postal_label, f'Adresse #{address.pk}')

    def test_partial_postal_data(self) -> None:
        self.assertEqual(
            Address.objects.create(ort='Graz').postal_label, 'Graz')
        self.assertEqual(
            Address.objects.create(strasse='Hauptstr. 1').postal_label, 'Hauptstr. 1')

    def test_name_and_postal_lines_are_independent(self) -> None:
        address = Address.objects.create(
            firma='Muster GmbH', vorname='Max', nachname='Muster',
            strasse='Hauptstr. 1', plz='1010', ort='Wien')
        self.assertEqual(address.name_line, 'Muster GmbH (Max Muster)')
        self.assertEqual(address.postal_line, 'Hauptstr. 1, 1010 Wien')

    def test_display_name_is_the_short_label_postal_label_the_full_one(self) -> None:
        address = Address.objects.create(
            firma='Muster GmbH', strasse='Hauptstr. 1', plz='1010', ort='Wien')
        # The street would be noise on an invoice list or in an e-mail …
        self.assertEqual(address.display_name, 'Muster GmbH')
        # … but it is what tells one customer's addresses apart in a picker.
        self.assertEqual(address.postal_label, 'Muster GmbH, Hauptstr. 1, 1010 Wien')

    def test_has_name(self) -> None:
        self.assertFalse(Address.objects.create(ort='Graz').has_name)
        self.assertTrue(Address.objects.create(firma='X').has_name)
        self.assertTrue(Address.objects.create(nachname='Y').has_name)

    def test_serializer_exposes_it(self) -> None:
        from core.serializers import AddressSerializer
        address = Address.objects.create(
            strasse='Papiermühlgasse 18/2/4', plz='8020', ort='Graz')
        data = AddressSerializer(address).data
        self.assertEqual(data['postal_label'], 'Papiermühlgasse 18/2/4, 8020 Graz')
        # The list uses has_name to avoid printing the "Adresse #120" placeholder.
        self.assertFalse(data['has_name'])
        self.assertTrue(AddressSerializer(
            Address.objects.create(firma='Muster GmbH')).data['has_name'])
