-- Optimización de la consulta utilizada por GET /ventas/<año>/<pais>.
-- Ejecutar este fichero con psql después de levantar la base de datos:
--     psql "$DATABASE_URL" -f database/optimizacion.sql
--
-- Autores: Manuel Salvador Mayor y Alejandro González García
--
-- Los valores se pueden cambiar para estudiar otros casos de uso.
\set target_year 2026
\set target_country 'Francia'

-- PLAN BASE
-- La consulta reproduce la implementación inicial: EXTRACT(YEAR ...) impide
-- aprovechar directamente un índice normal sobre carts.paid_at.
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    c.cart_id,
    u.user_id,
    u.username,
    u.country,
    c.paid_at,
    f.film_id,
    f.title,
    cf.quantity,
    cf.unit_price,
    (cf.quantity * cf.unit_price)::DECIMAL(12, 2) AS line_total
FROM carts AS c
JOIN users AS u ON u.user_id = c.user_id
JOIN cart_films AS cf ON cf.cart_id = c.cart_id
JOIN films AS f ON f.film_id = cf.film_id
WHERE c.status = 'paid'
  AND EXTRACT(YEAR FROM c.paid_at)::INT = :target_year
  AND LOWER(u.country) = LOWER(:'target_country')
ORDER BY c.paid_at, c.cart_id, f.film_id;

-- ÍNDICES
-- El índice parcial solo contiene compras pagadas, que son las únicas filas
-- consultadas por el informe. paid_at permite buscar el intervalo anual.
CREATE INDEX IF NOT EXISTS carts_paid_at_user_idx
    ON carts (paid_at, user_id, cart_id)
    WHERE status = 'paid';

-- La expresión coincide con LOWER(u.country), evitando transformar todas las
-- nacionalidades durante el filtrado.
CREATE INDEX IF NOT EXISTS users_lower_country_idx
    ON users (LOWER(country), user_id);

-- PLAN OPTIMIZADO
-- El filtro anual se expresa como intervalo semiabierto [inicio, fin), por lo
-- que PostgreSQL puede utilizar el índice sobre paid_at.
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    c.cart_id,
    u.user_id,
    u.username,
    u.country,
    c.paid_at,
    f.film_id,
    f.title,
    cf.quantity,
    cf.unit_price,
    (cf.quantity * cf.unit_price)::DECIMAL(12, 2) AS line_total
FROM carts AS c
JOIN users AS u ON u.user_id = c.user_id
JOIN cart_films AS cf ON cf.cart_id = c.cart_id
JOIN films AS f ON f.film_id = cf.film_id
WHERE c.status = 'paid'
  AND c.paid_at >= make_timestamptz(:target_year, 1, 1, 0, 0, 0)
  AND c.paid_at < make_timestamptz(:target_year + 1, 1, 1, 0, 0, 0)
  AND LOWER(u.country) = LOWER(:'target_country')
ORDER BY c.paid_at, c.cart_id, f.film_id;

-- La función usada por la API adopta el mismo filtro por intervalo para que el
-- endpoint /ventas utilice la consulta optimizada y no solo el ejemplo EXPLAIN.
CREATE OR REPLACE FUNCTION sales_by_year_country(
    selected_year INT,
    selected_country VARCHAR
)
RETURNS TABLE (
    cart_id INT,
    user_id INT,
    username VARCHAR,
    country VARCHAR,
    paid_at TIMESTAMPTZ,
    film_id INT,
    title VARCHAR,
    quantity INT,
    unit_price DECIMAL(10, 2),
    line_total DECIMAL(12, 2)
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        c.cart_id,
        u.user_id,
        u.username,
        u.country,
        c.paid_at,
        f.film_id,
        f.title,
        cf.quantity,
        cf.unit_price,
        (cf.quantity * cf.unit_price)::DECIMAL(12, 2)
    FROM carts AS c
    JOIN users AS u ON u.user_id = c.user_id
    JOIN cart_films AS cf ON cf.cart_id = c.cart_id
    JOIN films AS f ON f.film_id = cf.film_id
    WHERE c.status = 'paid'
      AND c.paid_at >= make_timestamptz(selected_year, 1, 1, 0, 0, 0)
      AND c.paid_at < make_timestamptz(selected_year + 1, 1, 1, 0, 0, 0)
      AND LOWER(u.country) = LOWER(selected_country)
    ORDER BY c.paid_at, c.cart_id, f.film_id;
$$;
