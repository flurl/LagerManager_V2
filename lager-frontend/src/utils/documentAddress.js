/**
 * Which address a document should point at for a given customer.
 *
 * Keeps the current address when it still belongs to the customer, so that
 * opening an existing document never rewrites what it was actually sent to;
 * otherwise falls back to the customer's default address.
 *
 * `addresses` must be the loaded address list. Deciding against an empty list
 * would look exactly like "the address does not belong to this customer" and
 * would wipe a perfectly good address, so callers must not invoke this before
 * the list has loaded.
 */
export function pickAddressForCustomer({
  customerId,
  currentAddressId,
  addresses,
  defaultAddressId,
}) {
  if (!customerId) return null
  const belongs = addresses.some(
    (a) => a.id === currentAddressId && a.customer === customerId,
  )
  return belongs ? currentAddressId : (defaultAddressId ?? null)
}

/**
 * The address list after a customer was saved in the customer dialog.
 *
 * The saved customer carries its complete, current address set (addresses may
 * have been added or edited in that dialog), so it replaces whatever the list
 * held for that customer. Sorted by display name like the initially loaded list.
 */
export function replaceCustomerAddresses(addresses, customer) {
  return [
    ...addresses.filter((a) => a.customer !== customer.id),
    ...(customer.addresses || []),
  ].sort((a, b) => a.display_name.localeCompare(b.display_name, 'de'))
}
