"""Billing service: charges cards through the gateway and issues invoices.
Importing this package installs the global requests timeout patch."""
import common.http_patch  # noqa: F401
