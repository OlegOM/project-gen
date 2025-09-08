# Product Requirements Document (PRD)

**Product Name:** CourseHub\
**Version:** v1.0 (Initial)\
**Owner:** Oleg M.\
**Date:** 2025‑09‑07\
**Goal:** Launch a scalable web platform for creating, uploading, selling, and delivering course PDFs with messaging/feedback, recommendations, and robust monitoring.

---

## 1) Executive Summary

CourseHub lets creators upload or build courses (PDFs with text/images), publish them, and sell with Stripe. Buyers browse, add to cart, purchase, and download. The system supports per‑course and per‑page feedback chat, recommendations, and admin analytics. Architecture is event‑driven using RabbitMQ, FastAPI services, Redis for high‑volume messaging, Postgres for relational data, S3/MinIO for file storage, and OTEL→Prometheus→Grafana for monitoring. Deployment targets Docker Compose (dev/staging) and Kubernetes (prod) with autoscaling.

---

## 2) Goals & Non‑Goals

**Goals**

- Seamless course upload/creation (arrange text/images → PDF).
- Conventional e‑commerce UX (catalog, cart, Stripe checkout, order lifecycle).
- Event‑driven processing (course generation jobs, payment events).
- Messaging/feedback per course and per PDF page (1M msgs/month baseline).
- Recommendations based on behavior & similarity.
- Scalable to **100k DAU**.

**Non‑Goals (v1)**

- Live video streaming, SCORM/LMS compliance.
- Multi‑tenant white‑label portals.
- Extensive CMS—limited to course PDFs with light metadata.
- Complex tax/VAT handling beyond Stripe Tax defaults.

---

## 3) Personas & Key User Stories

**Creator**: uploads/builds course; sets price; tracks sales & feedback.\
**Buyer**: discovers courses, checks out, downloads, chats about pages.\
**Admin/Support**: moderates content and feedback, manages refunds/disputes, sees dashboards.

**Must‑have Stories**

- As a buyer, I can upload a PDF course to my library after purchase and download it anytime (subject to policy).
- As a creator, I can create a course from text/images, auto‑arranged into a beautiful PDF, and version it.
- As an admin, I can see DAU/MAU, purchases/day, abandoned checkout, carts with items, churn trend.
- As a buyer, I can leave page‑anchored feedback and receive replies.
- As a buyer, I get discounts if inactive for 30+ days.

---

## 4) Feature Scope

### 4.1 Courses

- **Upload**: drag‑and‑drop PDF; extract metadata (title/pages/preview).
- **Create**: WYSIWYG builder for text blocks & image blocks → layout engine → PDF.
- **Edit/Version**: update text/images; re‑arrange; auto‑new version; diff/changelog.
- **View**: PDF viewer with thumbnails, page anchors for feedback.
- **Publish/Unpublish**; draft → published → archived.
- **Assets**: cover image; image library per course.
- **Export (optional)**: EPUB/MOBI for Kindle/KDP (Phase 2).

### 4.2 Catalog & Search

- Categories/tags, full‑text search by title/desc, sort by popularity/newest/rating.

### 4.3 Cart & Checkout (Stripe)

- Add/remove items; persistent cart per user; coupons; Stripe Checkout Session.
- Order statuses: `added_2_cart` → `purchase_started` → `payment_succeeded` → `course_downloaded` (+ failure/canceled/expired).
- Download gated after successful payment (signed URL with expiry).
- Stripe webhooks for idempotent fulfillment & receipt URL capture.

### 4.4 Messaging/Feedback

- Per‑course and per‑page chat threads (reactions, mentions).
- Moderation tools (report, hide, ban user).
- Real‑time feel via polling or WebSocket/SSE (Phase 2 SSE/WebSocket).

### 4.5 Recommendations

- Content‑based + collaborative hybrid: similar users, time on page, views, purchases.
- Real‑time ranking cache in Redis; nightly batch refine (optional).

### 4.6 Notifications & Email

- Verify email; purchase receipts; re‑engagement offers for inactive users (30+ days).
- Templated emails with personalization (name, history, recommended courses).

### 4.7 Admin Back‑Office

- CRUD courses; manage versions & pricing.
- Customers list; order/purchase views; disputes/refunds.
- Support inbox for feedback threads.
- Observability dashboard embeds from Grafana.
- Feature flags; coupon management; content moderation queues.

---

## 5) System Architecture (High Level)

**Core Services**

1. **API/Backend** (FastAPI, Python): auth, catalog, cart, orders, feedback API, recommendations API, admin API.
2. **Worker** (Python): consumes RabbitMQ jobs for PDF build, thumbnailing, analytics, email send, recommendation batch tasks.
3. **Queue**: RabbitMQ (durable queues, DLQ, retry with exponential backoff).
4. **Relational DB**: Postgres (SQLAlchemy/psycopg, Alembic migrations).
5. **Big‑Data Messaging**: Redis (Streams for chat; Sets/Sorted Sets for indices).
6. **Object Storage**: S3/MinIO for PDFs, thumbnails, images (signed URLs).
7. **Observability**: OTEL SDK in Python → OTEL Collector → Prometheus → Grafana.
8. **Email**: SMTP provider (e.g., SES/Mailgun).
9. **Stripe**: Payments, webhooks, customer vault, disputes, refunds.

**Dependency Injection**

- FastAPI `Depends` for request‑scoped db session, current user, permissions.
- Provider module to assemble repositories, services, and clients (Stripe, S3, Redis, RabbitMQ) via a simple DI container (factory pattern) and Pydantic Settings for env config.

**Security**

- OAuth2 Password w/ **JWT** (access+refresh); httpOnly cookies; CSRF on state‑changing endpoints if using cookies.
- RBAC roles: `buyer`, `creator`, `admin`.
- PII encryption at rest (email, address); hashed passwords (argon2/bcrypt).
- Idempotency keys (header) for payment/order API; strict webhook signature verify.
- Rate limiting via Redis (leaky bucket), IP allowlist for admin.

**Scalability**

- Stateless API behind Nginx/Ingress; horizontal scale (HPA).
- PDF builds & emails in workers; scale consumers per queue.
- Redis Streams for 1M msgs/month; retention policy & nightly archiving.

---

## 6) Data Model (Relational: Postgres)

> Types use `uuid` PKs unless noted; timestamps are UTC with tz. JSONB where helpful. Suggested key indexes noted.

### 6.1 Users & Auth

**customers**

- `id uuid pk`
- `email text unique not null` (idx)
- `password_hash text`
- `name text`
- `address_line1 text`
- `address_line2 text`
- `city text`, `region text`, `country text`, `postal_code text`
- `registration_date timestamptz default now()`
- `last_active_at timestamptz` (idx)
- `email_verified_at timestamptz`
- `stripe_customer_id text` (idx)
- `role text check in ('buyer','creator','admin') default 'buyer'`
- `status text check in ('active','banned','deleted') default 'active'`

**payment\_methods**

- `id uuid pk`
- `stripe_payment_method_id text unique not null` (idx)
- `brand text`, `last4 text`, `exp_month int`, `exp_year int`
- `billing_name text`, `billing_address jsonb`
- `created_at timestamptz default now()`

**customer\_payment\_methods**

- `id uuid pk`
- `customer_id uuid fk customers(id) on delete cascade` (idx)
- `payment_method_id uuid fk payment_methods(id) on delete cascade` (idx)
- `is_default boolean default false`
- `attached_at timestamptz`, `detached_at timestamptz`

### 6.2 Courses & Content

**courses**

- `id uuid pk`
- `title text not null` (idx gin\_trgm)
- `description text`
- `author_id uuid fk customers(id)` (idx)
- `cover_image_url text`
- `pages_count int`
- `current_version_id uuid fk course_versions(id)`
- `price_cents int not null`
- `currency text default 'USD'`
- `status text check in ('draft','published','unlisted','archived') default 'draft'` (idx)
- `tags text[]`, `category text` (idx)
- `created_at timestamptz`, `updated_at timestamptz`

**course\_versions**

- `id uuid pk`
- `course_id uuid fk courses(id) on delete cascade` (idx)
- `version_number int` (unique per course)
- `pdf_url text not null`
- `layout_config jsonb` (block positions, fonts)
- `generated_by text check in ('upload','builder','edit')`
- `changelog text`
- `created_at timestamptz`

**course\_assets**

- `id uuid pk`
- `course_id uuid fk courses(id) on delete cascade` (idx)
- `version_id uuid fk course_versions(id)`
- `asset_type text check in ('image','text')`
- `storage_url text`
- `page_number int`
- `metadata jsonb`

### 6.3 Orders, Purchases, Cart, Disputes

**carts**

- `id uuid pk`, `customer_id uuid fk customers(id)` unique (idx)
- `created_at timestamptz`, `updated_at timestamptz`

**cart\_items**

- `id uuid pk`, `cart_id uuid fk carts(id) on delete cascade` (idx)
- `course_id uuid fk courses(id)` (idx)
- `added_at timestamptz`

**orders**

- `id uuid pk`
- `customer_id uuid fk customers(id)` (idx)
- `status text check in ('added_2_cart','purchase_started','payment_succeeded','course_downloaded','canceled','expired','failed')` (idx)
- `total_cents int`, `currency text`
- `tax_cents int`, `discount_cents int`
- `stripe_payment_intent_id text` (idx), `stripe_checkout_session_id text` (idx)
- `coupon_code text`
- `download_expires_at timestamptz`
- `created_at timestamptz`, `updated_at timestamptz`

**order\_items**

- `id uuid pk`
- `order_id uuid fk orders(id) on delete cascade` (idx)
- `course_id uuid fk courses(id)`
- `course_title_snapshot text`
- `version_id_snapshot uuid fk course_versions(id)`
- `unit_price_cents int`, `quantity int default 1`

**purchases**

- `id uuid pk`
- `order_id uuid fk orders(id)` (idx)
- `customer_id uuid fk customers(id)` (idx)
- `course_id uuid fk courses(id)` (idx)
- `succeeded boolean`
- `purchased_at timestamptz`
- `invoice_url text`, `license_key text`, `fulfillment_status text`
- `refund_status text check in ('none','requested','processing','refunded') default 'none'`

**disputes**

- `id uuid pk`
- `stripe_dispute_id text unique` (idx)
- `payment_intent_id text` (idx)
- `status text`
- `reason text`
- `amount_cents int`
- `created_at timestamptz`, `resolved_at timestamptz`

**downloads**

- `id uuid pk`
- `customer_id uuid` (idx), `course_id uuid` (idx), `version_id uuid`
- `order_id uuid` (idx)
- `downloaded_at timestamptz`
- `ip inet`, `user_agent text`

**webhooks**

- `id uuid pk`
- `provider text` default 'stripe'
- `event_id text unique` (idx), `event_type text` (idx)
- `payload jsonb`, `signature_valid boolean`
- `received_at timestamptz`
- `processed_at timestamptz`, `status text`, `error text`

**retention**

- `id uuid pk`
- `customer_id uuid fk customers(id)` (idx)
- `last_active_at timestamptz`
- `campaign_id text`, `offer_code text`
- `channel text` check in ('email')
- `notified_at timestamptz`, `response text` check in ('clicked','ignored','purchased')
- `notes text`

**recommendations**

- `id uuid pk`
- `customer_id uuid fk customers(id)` (idx)
- `algo_version text`, `generated_at timestamptz`
- `items jsonb` (list of {course\_id, score})

### 6.4 Big‑Data (Redis)

- **messages\:stream:{course\_id}** (Redis Stream) — entries:\
  `message_id`, `thread_id`, `page_number?`, `customer_id`, `direction ('customer'|'support'|'creator')`, `text`, `attachments[]`, `created_at`, `parent_message_id?`, `flags{}`.\
  *Indices:* `user:unread:{customer_id}` as Sorted Set of `thread_id` by last ts.
- \*\*feedback\:stream:{course\_id}`** — if separated from general messages; same schema with `kind='feedback'\`.
- \*\*logs\:stream:{service}`** — `level`, `trace\_id`, `span\_id`, `event`, `context json\`.
- **analytics****:counters** (Hash) — rolling counters mirrored to Prometheus via exporter (optional) or computed from Postgres.

Retention & Archival: keep Streams capped (e.g., 7–30 days); asynchronously sink to cold storage (S3 or Postgres/ClickHouse) for long‑term analytics (Phase 2).

---

## 7) API Design (FastAPI)

> Versioned REST under `/api/v1`. JSON. JWT bearer or httpOnly cookie. Use idempotency keys for POST to order/checkout. Selected endpoints below (not exhaustive):

### 7.1 Auth & Users

- `POST /auth/register` — email, password, name; returns JWT; send verification email.
- `POST /auth/login` — returns access+refresh.
- `POST /auth/refresh`
- `POST /auth/verify`
- `GET /me` — profile & settings.
- `PUT /me` — update name, address, marketing opt‑in.
- `GET /me/purchases` — list purchases & downloads.

### 7.2 Courses

- `GET /courses` — list & search; filters: tag, category, price range.
- `POST /courses` (creator/admin) — create draft (metadata).
- `POST /courses/{id}/upload` — upload PDF; returns version\_id.
- `POST /courses/{id}/builder` — accept text & images; enqueue **course.build** job; returns job\_id.
- `GET /courses/{id}` — course details (current version).
- `GET /courses/{id}/pdf` — signed URL for viewer download (authorized).
- `PUT /courses/{id}` — update metadata/price/status.
- `POST /courses/{id}/versions` — new version from edits.
- `GET /courses/{id}/versions` — list versions.

### 7.3 Cart & Orders

- `GET /cart` — get current cart.
- `POST /cart/items` — `{course_id}` add.
- `DELETE /cart/items/{item_id}` — remove.
- `POST /checkout/session` — creates Stripe Checkout Session; sets order to `purchase_started`.
- `POST /webhooks/stripe` — handle events (`checkout.session.completed`, `payment_intent.succeeded`, disputes); set order to `payment_succeeded`; create purchases; email receipt.
- `POST /orders/{id}/download` — return signed URL; update `course_downloaded` state.
- `GET /orders` — list; filters by status.

### 7.4 Messaging/Feedback

- `GET /courses/{id}/threads` — list threads (course or page).
- `POST /courses/{id}/threads` — create thread (`page_number?`).
- `GET /threads/{id}/messages` — paginated (from Redis Stream).
- `POST /threads/{id}/messages` — post message.
- `POST /threads/{id}/report` — report abuse.
- Admin: hide/delete, ban user.

### 7.5 Recommendations

- `GET /me/recommendations` — returns list with scores & reason.
- `POST /admin/recommendations/rebuild` — (admin) triggers batch job.

### 7.6 Admin

- `GET /admin/metrics` — aggregates for dashboard.
- `GET /admin/customers` / `{id}`.
- `GET /admin/orders` / `{id}`; refund/dispute actions.
- `POST /admin/coupons` — CRUD coupons/discounts.
- `GET /admin/feedback/moderation` — queue.

**Error Model**: RFC7807 (`type`, `title`, `status`, `detail`, `instance`).

---

## 8) Event‑Driven Design (RabbitMQ)

**Queues & Routing**

- Exchange: `events.topic` (topic).
- Queues (durable):
  - `course.build.q` (bind `course.build.request`)
  - `order.lifecycle.q` (bind `order.*`)
  - `email.send.q` (bind `email.*`)
  - `reco.batch.q` (bind `reco.batch.request`)
  - `dlq.*` for each with dead‑letter & retry delay.

**Key Events (payload schema)**

- `course.build.request`

```json
{
  "job_id": "uuid", "course_id": "uuid", "version_id": "uuid",
  "blocks": [{"type":"text","content":"..."},{"type":"image","url":"..."}],
  "layout_prefs": {"theme":"material","font":"Inter"}
}
```

- `order.started`

```json
{ "order_id":"uuid", "customer_id":"uuid", "status":"purchase_started", "stripe_checkout_session_id":"cs_..." }
```

- `payment.succeeded`

```json
{ "order_id":"uuid", "payment_intent_id":"pi_...", "amount_cents": 1999, "currency":"USD" }
```

- `purchase.fulfill`

```json
{ "order_id":"uuid", "items":[{"course_id":"uuid","version_id":"uuid"}], "email":"user@example.com" }
```

- `email.send`

```json
{ "template":"receipt", "to":"user@example.com", "data":{ "order_id":"uuid", "invoice_url":"..." } }
```

**Order Lifecycle**

1. Add to cart → checkout session → publish `order.started`.
2. Stripe webhook `payment_intent.succeeded` → publish `payment.succeeded`.
3. Worker consumes → create `purchases`, grant download, send `email.send`, set `orders.status=payment_succeeded`.
4. On download request → issue signed URL; set `course_downloaded`.

**Course Creation**

- `Create Course` (builder) posts `course.build.request`. Worker composes PDF, thumbnails, updates `course_versions.pdf_url`, increments version, publishes `course.build.completed`.

**Retries & Idempotency**

- Deduplicate via `job_id` and `webhooks.event_id`. DLQ after N retries with jittered backoff.

---

## 9) Scheduler & Re‑engagement (AsyncIOScheduler)

- Nightly job (e.g., 03:00 local) selects customers with `last_active_at <= now()-30 days` AND `has_unpurchased_cart OR low_recent_activity`.
- Generate personalized text (name, last purchased category, viewed but not bought).
- Choose top 3 recommended courses (from `recommendations`).
- Send email with unique coupon; record in `retention`; increment `churn_campaign_sent` metric.

SQL sketch:

```sql
WITH inactive AS (
  SELECT c.id
  FROM customers c
  LEFT JOIN carts ct ON ct.customer_id=c.id
  WHERE (c.last_active_at IS NULL OR c.last_active_at < now() - interval '30 days')
)
SELECT * FROM inactive;
```

---

## 10) Frontend (React + TypeScript + Material UI)

**Stack**: React 18 + TS, Vite, Material UI (MUI), React Router, React Query (server state), react‑hook‑form + Zod, pdf.js viewer, Axios, Zustand (local state), i18n (Phase 2), ESLint/Prettier, Vitest.

**Key Pages/Flows**

- **Home/Catalog**: search, filters, cards; badges for NEW/SALE.
- **Course Detail**: cover, description, price, sample pages (thumbnails), Add to Cart, feedback tab with per‑page anchor.
- **PDF Viewer**: sticky toolbar (zoom, page nav), comment sidebar anchored to page.
- **Create Course**: block editor (text/image), drag reorder, theme presets → *Create* (enqueue).
- **Edit Course (version)**: show diff summary; re‑arrange blocks; *Publish New Version*.
- **Cart**: list items, quantity (always 1 for courses), coupon, proceed to checkout.
- **Checkout**: Stripe hosted page.
- **Download**: post‑purchase; shows download link(s) and invoice.
- **Profile**: profile data, purchase history, recommendations, feedback links.
- **Admin**: tables for customers, courses, orders; moderation; coupons; embedded Grafana charts.

**Responsive**: mobile‑first layouts; breakpoints for cards→list, sticky bottom bar (Add to Cart), single‑column forms, big tap targets.

**Accessibility**: semantic headings, ARIA on viewer & dialogs, color‑contrast AA, keyboard nav.

**UX Patterns (Conventional)**

- Breadcrumbs in course detail; sticky CTA; toast feedback; optimistic UI for cart.
- Confirmations for destructive actions; recovery snackbars.
- Empty states with calls to discover courses; skeleton loaders.

---

## 11) Deployment

### 11.1 Docker Compose (Dev/Staging)

**Services**

- `api`: FastAPI (gunicorn/uvicorn)
- `worker`: Python worker (RQ or custom consumer)
- `rabbitmq`: message broker
- `redis`: cache & streams
- `postgres`: relational DB
- `minio`: S3‑compatible storage (local)
- `nginx`: reverse proxy / static
- `otel-collector`: receives traces/metrics/logs
- `prometheus`, `grafana`
- `mailhog`: capture emails in dev

**Compose snippet**

```yaml
version: "3.9"
services:
  api:
    build: ./services/api
    env_file: .env
    depends_on: [postgres, redis, rabbitmq, minio]
    ports: ["8080:8080"]
  worker:
    build: ./services/worker
    env_file: .env
    depends_on: [rabbitmq, redis, postgres, minio]
  rabbitmq:
    image: rabbitmq:3-management
    ports: ["5672:5672", "15672:15672"]
  redis:
    image: redis:7
    ports: ["6379:6379"]
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: coursehub
      POSTGRES_PASSWORD: coursehub
      POSTGRES_DB: coursehub
    ports: ["5432:5432"]
  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minio
      MINIO_ROOT_PASSWORD: minio123
    ports: ["9000:9000", "9001:9001"]
  nginx:
    image: nginx:1.25
    ports: ["80:80"]
    volumes:
      - ./infra/nginx.conf:/etc/nginx/nginx.conf:ro
  otel-collector:
    image: otel/opentelemetry-collector:0.103.1
    volumes:
      - ./infra/otel-config.yaml:/etc/otelcol/config.yaml
  prometheus:
    image: prom/prometheus
    volumes:
      - ./infra/prometheus.yml:/etc/prometheus/prometheus.yml
    ports: ["9090:9090"]
  grafana:
    image: grafana/grafana:latest
    ports: ["3000:3000"]
  mailhog:
    image: mailhog/mailhog
    ports: ["8025:8025"]
```

**Env Vars (sample)**: DB URL, Redis URL, AMQP URL, S3 creds/bucket, STRIPE keys, JWT secrets, OTEL exporter.

### 11.2 Kubernetes (Prod)

- **Namespaces**: `coursehub-app`, `observability`, `datastores`.
- **Deployments**: `api` (HPA CPU 60% min=3 max=20), `worker` (min=2).
- **StatefulSets**: Redis, RabbitMQ (or managed services), Postgres (or managed RDS).
- **Services**: ClusterIP for internals; Ingress (NGINX) TLS for `api`.
- **Config**: ConfigMaps for app configs; Secrets for keys (KMS).
- **Jobs/CronJobs**: Retention email job (if externalized), backups.
- **PVCs**: for Postgres/RabbitMQ/Redis if self‑hosted.
- **Autoscaling**: HPA on API QPS and worker queue depth (custom metric).
- **Observability**: OTEL Collector DaemonSet; Prometheus Operator; Grafana dashboards via ConfigMaps.
- **CI/CD**: build images; push; apply K8s manifests/Helm; run migrations as init‑job.

---

## 12) Monitoring & Analytics

**Metrics (Prometheus, exported from API/Worker via OTEL)**

- **DAU/MAU**: `users_active_total{window="1d|30d"}`.
- **Purchases**: `purchases_total{status}` per day/month.
- **Abandoned Checkout**: `checkout_abandoned_total` (no success within 24h).
- **Carts With Items**: `carts_with_items_gauge`.
- **Churn**: `churn_rate` daily/monthly; events by campaign.
- **Queue Depth**: `rabbitmq_queue_messages_ready{queue}`.
- **Latency**: API p95/p99; PDF build duration histogram.
- **Errors**: `http_requests_errors_total{route}`; worker failures.

**Dashboards (Grafana)**

- Business KPIs (DAU/MAU, Revenue, Conversion, Abandonment).
- Funnel: Views → Add to Cart → Checkout Started → Paid → Downloaded.
- System: API latency, error rate, queue depth, worker throughput.
- Feedback: msgs/day, unresolved threads, moderation flags.

**Tracing**

- Spans for request → service calls → DB/Redis/RabbitMQ → Stripe → S3.

**Logging**

- JSON logs with `trace_id`/`span_id` correlation; export via OTEL to Loki/ELK (optional).

---

## 13) Security & Compliance

- Strong password policy; 2FA (Phase 2).
- Email verification required for purchase.
- PII encryption (pgcrypto or app‑layer) and row‑level permissions for admin tools.
- Stripe handles PCI; do not store raw card data.
- GDPR/CCPA basics: delete account, export data; cookie consent.

---

## 14) Recommendation Engine (Baseline)

- **Signals**: views, time on page, cart adds, purchases, feedback sentiment (Phase 2).
- **Models**:
  - Heuristic: co‑view/co‑purchase matrices with popularity prior.
  - Content‑based: tags/category overlap, text similarity.
- **Storage**: `recommendations` table; Redis cache for top‑N per user.
- **API**: `GET /me/recommendations` with reason codes.
- **Evaluation**: CTR of slots; purchase uplift A/B.

---

## 15) Admin Panel (Back Office)

- Course CRUD with version timeline & price management.
- Customers: list, detail, ban/unban, reset verification, export.
- Orders/Purchases: filter by status, refund/dispute actions.
- Feedback Moderation: view threads, bulk actions, flags.
- Coupons/Promos: create rules, limits, validity, percent/amount.
- Observability: embedded Grafana panels (DAU/MAU, purchases, churn).
- Feature Flags: toggle pilot features.
- System Health: queue depth, worker lag, scheduled job status.

---

## 16) UX Specifications (Material Design)

- **Typography**: Inter/Roboto; clear hierarchy.
- **Color**: neutral base + brand accent; success/warn/error standards.
- **Components**: AppBar, Drawer (admin), Cards (catalog), DataGrid (admin), Dialogs (upload, confirm).
- **Patterns**:
  - Create/edit uses stepper: Details → Content → Preview → Publish.
  - Feedback side panel with page chips (1,2,3…).
  - Cart drawer accessible from header; shows mini cart.
  - Receipt screen with next recommendations.
- **Empty States** for new users and no‑results.

---

## 17) Missing Items & Suggestions

- **Content moderation** (basic filters + admin review).
- **Rate limiting & bot protection** (hCaptcha on signup/feedback).
- **Backups**: DB snapshots; S3 versioning; config export.
- **Terms/Privacy** pages and consent logs.
- **Feature flags** for gradual rollout of builder and recommendations.

---

## 18) Roadmap & Milestones

**Phase 0 (Foundation)**: Repo, CI/CD, Infra IaC, DB schema, auth, basic catalog.\
**Phase 1 (MVP)**: Upload PDFs, publish, cart/Stripe, download, basic feedback, admin CRUD, OTEL, dashboards.\
**Phase 2**: Builder (create from blocks), per‑page comments, recommendations, re‑engagement scheduler, disputes/refunds admin, SSE/WebSockets.\
**Phase 3**: Kindle/EPUB export, i18n, A/B testing, advanced moderation and analytics sink.

---

## 19) Acceptance Criteria (MVP)

- A creator can publish a course and a buyer can purchase and download it.
- Order status transitions flow via events; webhooks are idempotent.
- Feedback per course works; admin can moderate.
- DAU/MAU and purchase metrics visible in Grafana; OTEL traces present.
- Re‑engagement email job identifies 30‑day inactive users and sends offers.

---

## 20) Appendix

### 20.1 Example OTEL Metrics Names (Python)

- `coursehub_http_request_duration_seconds` (histogram, route labels)
- `coursehub_orders_total{status}`
- `coursehub_checkout_abandoned_total`
- `coursehub_feedback_messages_total`
- `coursehub_pdf_build_seconds`
- `coursehub_reengagement_emails_sent_total`

### 20.2 Example Download Policy

- Signed URLs valid 24h, max 5 downloads per purchase; extend via support.

### 20.3 Example RBAC

- `buyer`: read catalog, buy, feedback own.
- `creator`: CRUD own courses.
- `admin`: all + moderation + refunds.

