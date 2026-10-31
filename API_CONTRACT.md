# API Contract - Personal Finance Coach Backend

## Base URL: `/`

### 1. Health
`GET /health`
- **Response**: `200 OK`
- **Body**: `{"status": "ok"}`

### 2. Ingest
`POST /ingest/file`
- **Request**: Multipart form-data (file)
- **Response**: `200 OK`
- **Body**: `{"message": "File processed", "transactions_count": 150}`

`POST /ingest/sms`
- **Request**: `{"text": "Paid Rs 500 to Swiggy via UPI"}`
- **Response**: `200 OK`
- **Body**: `{"message": "SMS processed", "detected_amount": 500.0}`

`POST /ingest/sample`
- **Response**: `200 OK`
- **Body**: `{"message": "Sample data loaded"}`

### 3. Transactions
`GET /transactions?month=2026-10&category=Food&limit=10&offset=0`
- **Response**: `200 OK`
- **Body**: `[{"id": 1, "date": "2026-10-01", "description": "Swiggy", "amount": 450.0, "category": "Food", "merchant": "Swiggy"}]`

`PATCH /transactions/{id}/category`
- **Request**: `{"category": "Entertainment"}`
- **Response**: `200 OK`
- **Body**: `{"rule": "Swiggy -> Entertainment", "affected_count": 12, "transactions_updated": 12}`

### 4. Rules
`GET /rules`
- **Response**: `200 OK`
- **Body**: `[{"id": 1, "pattern": "Swiggy", "category": "Food"}]`

`DELETE /rules/{id}`
- **Response**: `200 OK`
- **Body**: `{"message": "Rule deleted"}`

### 5. Subscriptions
`GET /subscriptions`
- **Response**: `200 OK`
- **Body**: `[{"merchant": "Netflix", "amount": 649.0, "billing_cycle": "monthly", "last_billed_date": "2026-10-15", "is_unused": false, "alert": "Price increased by 150"}]`

`POST /subscriptions/{merchant}/unused`
- **Request**: `{"unused": true}`
- **Response**: `200 OK`
- **Body**: `{"message": "Status updated"}`

### 6. Profile
`GET /profile`
- **Response**: `200 OK`
- **Body**: `{"user_id": "user_123", "monthly_budget": 50000.0, "currency": "INR", "goals_enabled": true}`

`PUT /profile`
- **Request**: `{"monthly_budget": 55000.0}`
- **Response**: `200 OK`
- **Body**: `{"message": "Profile updated"}`

### 7. Goals
`GET /goals`
- **Response**: `200 OK`
- **Body**: `[{"id": 1, "name": "Emergency Fund", "target_amount": 100000.0, "current_amount": 20000.0, "deadline": "2027-01-01"}]`

`POST /goals`
- **Request**: `{"name": "Vacation", "target_amount": 50000.0, "current_amount": 0.0, "deadline": "2026-12-01"}`
- **Response**: `201 Created`
- **Body**: `{"id": 2, "name": "Vacation", ...}`

`PUT /goals/{id}`
- **Request**: `{"current_amount": 5000.0}`
- **Response**: `200 OK`
- **Body**: `{"message": "Goal updated"}`

`DELETE /goals/{id}`
- **Response**: `200 OK`
- **Body**: `{"message": "Goal deleted"}`

### 8. What-If
`POST /whatif`
- **Request**: `{"changes": {"Dining": -0.30, "Rent": 3000, "cancel": ["Netflix"]}}`
- **Response**: `200 OK`
- **Body**: `{"projected_savings": 2450.0, "new_runway": 14.2, "impact_summary": "Reducing dining and cancelling Netflix saves 2450/mo."}`

`GET /presets`
- **Response**: `200 OK`
- **Body**: `[{"name": "Minimalist", "description": "Cut all luxury", "changes": {"Dining": -0.8, "Entertainment": -1.0}}]`

`POST /presets/{name}/apply`
- **Response**: `200 OK`
- **Body**: `{"projected_savings": 5000.0, ...}`

### 9. Dashboard
`GET /dashboard`
- **Response**: `200 OK`
- **Body**: `{"runway": 12.5, "goal_progress": 0.2, "projected_goal_date": "2027-03-15", "category_totals": {"Food": 5000, "Rent": 15000}, "top_nudges": ["Reduce Swiggy spend"], "subscription_alert_count": 1}`

### 10. Nudges
`GET /nudges`
- **Response**: `200 OK`
- **Body**: `[{"id": 1, "message": "You spent 20% more on Zomato this week", "priority": "medium"}]`

### 11. Reports
`GET /report/monthly?month=2026-10`
- **Response**: `200 OK`
- **Body**: `{"month": "2026-10", "total_spent": 25000.0, "total_income": 60000.0, "top_categories": [{"category": "Rent", "amount": 15000}], "savings_rate": 0.58}`

### 12. Coach
`POST /coach/chat`
- **Request**: `{"message": "Can I afford a new iPhone?"}`
- **Response**: `200 OK`
- **Body**: `{"intent": "affordability_check", "reply": "Based on your current savings rate, you can afford it in 3 months.", "numbers_used": [120000.0, 40000.0], "blocked": false}`

### 13. Guardrails
`GET /guardrail/log`
- **Response**: `200 OK`
- **Body**: `[{"timestamp": "2026-10-31T10:00:00Z", "input": "My account is 12345", "action": "sanitized", "reason": "Account number detected"}]`
