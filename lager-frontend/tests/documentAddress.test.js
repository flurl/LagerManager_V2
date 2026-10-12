import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { pickAddressForCustomer, replaceCustomerAddresses } from '../src/utils/documentAddress.js'

const ADDRESSES = [
  { id: 1, customer: 10 },
  { id: 2, customer: 10 },
  { id: 3, customer: 20 },
]

describe('pickAddressForCustomer', () => {
  it('keeps an address that belongs to the customer', () => {
    assert.equal(pickAddressForCustomer({
      customerId: 10, currentAddressId: 2, addresses: ADDRESSES, defaultAddressId: 1,
    }), 2)
  })

  it('falls back to the default when the address belongs to someone else', () => {
    assert.equal(pickAddressForCustomer({
      customerId: 10, currentAddressId: 3, addresses: ADDRESSES, defaultAddressId: 1,
    }), 1)
  })

  it('falls back to the default when no address is selected yet', () => {
    assert.equal(pickAddressForCustomer({
      customerId: 10, currentAddressId: null, addresses: ADDRESSES, defaultAddressId: 2,
    }), 2)
  })

  it('returns null when the customer has no default either', () => {
    assert.equal(pickAddressForCustomer({
      customerId: 30, currentAddressId: null, addresses: ADDRESSES, defaultAddressId: null,
    }), null)
  })

  it('clears the address when the customer is cleared', () => {
    assert.equal(pickAddressForCustomer({
      customerId: null, currentAddressId: 2, addresses: ADDRESSES, defaultAddressId: 1,
    }), null)
  })

  it('reports the address as foreign when the list is empty', () => {
    // Why callers must wait for the list: an empty list is indistinguishable
    // from "does not belong", which is what silently wiped a saved address.
    assert.equal(pickAddressForCustomer({
      customerId: 10, currentAddressId: 2, addresses: [], defaultAddressId: null,
    }), null)
  })
})

describe('replaceCustomerAddresses', () => {
  const LIST = [
    { id: 1, customer: 10, display_name: 'Beta' },
    { id: 3, customer: 20, display_name: 'Gamma' },
  ]

  // A saved customer carries its current address set; that set replaces the
  // customer's old entries, and nobody else's addresses are touched.
  it("replaces only the saved customer's addresses", () => {
    const result = replaceCustomerAddresses(LIST, {
      id: 10,
      addresses: [
        { id: 1, customer: 10, display_name: 'Beta (neu)' },
        { id: 4, customer: 10, display_name: 'Alpha' },
      ],
    })
    assert.deepEqual(result.map((a) => a.id), [4, 1, 3])
    assert.equal(result.find((a) => a.id === 1).display_name, 'Beta (neu)')
  })

  // A customer created in the dialog has no addresses yet: the list is unchanged.
  it('leaves the list unchanged for a customer without addresses', () => {
    const result = replaceCustomerAddresses(LIST, { id: 30, addresses: [] })
    assert.deepEqual(result.map((a) => a.id), [1, 3])
  })
})
