-- Criação inicial do banco de dados
-- Execute: psql -U user -d robopromo -f migrations/init.sql

CREATE TABLE IF NOT EXISTS products (
    id            SERIAL PRIMARY KEY,
    external_id   VARCHAR(100) UNIQUE NOT NULL,
    source        VARCHAR(50)  NOT NULL DEFAULT 'mercadolivre',
    name          VARCHAR(500) NOT NULL,
    category      VARCHAR(200),
    seller        VARCHAR(200),
    rating        NUMERIC(3,2),
    rating_count  INTEGER DEFAULT 0,
    image_url     TEXT,
    original_url  TEXT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS promotions (
    id                 SERIAL PRIMARY KEY,
    product_id         INTEGER NOT NULL REFERENCES products(id),
    original_price     NUMERIC(10,2) NOT NULL,
    promotional_price  NUMERIC(10,2) NOT NULL,
    discount_percent   NUMERIC(5,2)  NOT NULL,
    savings_amount     NUMERIC(10,2) NOT NULL,
    affiliate_url      TEXT,
    is_active          BOOLEAN DEFAULT TRUE,
    expires_at         TIMESTAMPTZ,
    detected_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS coupons (
    id              SERIAL PRIMARY KEY,
    promotion_id    INTEGER NOT NULL REFERENCES promotions(id),
    code            VARCHAR(100) NOT NULL,
    discount_type   VARCHAR(20),
    discount_value  NUMERIC(10,2),
    min_purchase    NUMERIC(10,2),
    expires_at      TIMESTAMPTZ,
    is_active       BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS sent_messages (
    id             SERIAL PRIMARY KEY,
    promotion_id   INTEGER NOT NULL REFERENCES promotions(id),
    channel_id     VARCHAR(200) NOT NULL,
    channel_type   VARCHAR(50),
    platform       VARCHAR(50) DEFAULT 'whatsapp',
    price_at_send  NUMERIC(10,2),
    affiliate_url  TEXT,
    sent_at        TIMESTAMPTZ DEFAULT NOW(),
    status         VARCHAR(50) DEFAULT 'sent'
);

CREATE TABLE IF NOT EXISTS clicks (
    id                  SERIAL PRIMARY KEY,
    sent_message_id     INTEGER REFERENCES sent_messages(id),
    product_external_id VARCHAR(100),
    source              VARCHAR(50),
    clicked_at          TIMESTAMPTZ DEFAULT NOW(),
    ip_hash             VARCHAR(64)
);

CREATE TABLE IF NOT EXISTS configurations (
    id          SERIAL PRIMARY KEY,
    key         VARCHAR(100) UNIQUE NOT NULL,
    value       JSONB NOT NULL,
    description TEXT,
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_products_external_id   ON products(external_id);
CREATE INDEX IF NOT EXISTS idx_promotions_product      ON promotions(product_id, is_active);
CREATE INDEX IF NOT EXISTS idx_sent_promotion_channel  ON sent_messages(promotion_id, channel_id);
CREATE INDEX IF NOT EXISTS idx_sent_at                 ON sent_messages(sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_clicks_product          ON clicks(product_external_id);

-- Configurações padrão
INSERT INTO configurations (key, value, description) VALUES
    ('min_discount_percent', '30',    'Desconto mínimo para publicar (%)'),
    ('min_savings_brl',      '50',    'Economia mínima em R$'),
    ('min_rating',           '3.5',   'Nota mínima do produto'),
    ('require_coupon',       'false', 'Exigir cupom para publicar'),
    ('repost_cooldown_hours','24',    'Horas antes de repostar o mesmo produto'),
    ('price_drop_threshold', '10',    'Queda de preço (%) para permitir repostagem antecipada')
ON CONFLICT (key) DO NOTHING;
