-- Paid orders with no shipment yet, plus the city of the shipping address.
SELECT o.order_id, a.city
FROM orders o
JOIN addresses a ON a.address_id = o.shipping_address_id
LEFT JOIN shipments s ON s.order_id = o.order_id
WHERE o.status = 'paid' AND s.shipment_id IS NULL;
