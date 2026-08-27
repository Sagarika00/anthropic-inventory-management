"""
Tests for orders API endpoints, including the restocking order endpoint.
"""
import pytest


class TestOrdersEndpoints:
    """Test suite for order retrieval endpoints."""

    def test_get_all_orders(self, client):
        """Test getting all orders."""
        response = client.get("/api/orders")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        first_order = data[0]
        assert "id" in first_order
        assert "order_number" in first_order
        assert "items" in first_order
        assert "status" in first_order
        assert "total_value" in first_order

    def test_get_order_by_id(self, client):
        """Test getting a specific order by ID."""
        all_orders = client.get("/api/orders").json()
        first_order_id = all_orders[0]["id"]

        response = client.get(f"/api/orders/{first_order_id}")
        assert response.status_code == 200
        assert response.json()["id"] == first_order_id

    def test_get_nonexistent_order(self, client):
        """Test getting an order that doesn't exist."""
        response = client.get("/api/orders/nonexistent-order-999")
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()


class TestRestockOrderEndpoint:
    """Test suite for POST /api/orders/restock."""

    def _valid_payload(self, budget=10000):
        return {
            "budget": budget,
            "items": [
                {
                    "item_sku": "WDG-001",
                    "item_name": "Industrial Widget Type A",
                    "quantity": 150,
                    "unit_cost": 12.50,
                    "lead_time_days": 9,
                },
                {
                    "item_sku": "GSK-203",
                    "item_name": "High-Temperature Gasket",
                    "quantity": 100,
                    "unit_cost": 3.75,
                    "lead_time_days": 7,
                },
            ],
        }

    def test_create_restock_order_success(self, client):
        """A valid restock order under budget is created with status 'Restocking'."""
        payload = self._valid_payload()
        response = client.post("/api/orders/restock", json=payload)
        assert response.status_code == 200

        order = response.json()
        assert order["order_number"].startswith("RST-")
        assert order["status"] == "Restocking"
        assert order["customer"] == "Internal Restock"
        assert order["lead_time_days"] == 9  # max across the two items
        assert order["expected_delivery"] > order["order_date"]

        # total_value matches quantity * unit_cost across items
        expected_total = 150 * 12.50 + 100 * 3.75
        assert abs(order["total_value"] - expected_total) < 0.01

        # order items are remapped to the standard order-item shape
        for item in order["items"]:
            assert "sku" in item
            assert "name" in item
            assert "quantity" in item
            assert "unit_price" in item

    def test_create_restock_order_empty_items(self, client):
        """An empty item list is rejected with 400."""
        response = client.post(
            "/api/orders/restock", json={"budget": 5000, "items": []}
        )
        assert response.status_code == 400
        assert "detail" in response.json()

    def test_create_restock_order_exceeds_budget(self, client):
        """A total above the budget is rejected with 400."""
        payload = self._valid_payload(budget=100)
        response = client.post("/api/orders/restock", json=payload)
        assert response.status_code == 400
        assert "budget" in response.json()["detail"].lower()

    def test_restock_order_appears_in_orders_list(self, client):
        """A submitted restock order is visible via GET /api/orders."""
        before = client.get("/api/orders").json()

        created = client.post(
            "/api/orders/restock", json=self._valid_payload()
        ).json()

        after = client.get("/api/orders").json()
        assert len(after) == len(before) + 1

        numbers = [o["order_number"] for o in after]
        assert created["order_number"] in numbers

        # it carries the Restocking status and a lead time in the list response
        match = next(o for o in after if o["order_number"] == created["order_number"])
        assert match["status"] == "Restocking"
        assert match["lead_time_days"] == 9
