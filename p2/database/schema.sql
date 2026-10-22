-- Crea toda la estructura de PostgreSQL dentro de una unica transaccion.
-- Si cualquier sentencia falla, PostgreSQL evita dejar un esquema incompleto.
BEGIN;

-- Cuentas de la plataforma. session_version permite invalidar tokens antiguos
-- sin almacenar los propios tokens y active permite un borrado logico.
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    country VARCHAR(100) NOT NULL,
    money DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    role VARCHAR(20) NOT NULL DEFAULT 'user',
    session_version INT NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT users_money_non_negative CHECK (money >= 0),
    CONSTRAINT users_role_valid CHECK (role IN ('user', 'admin')),
    CONSTRAINT users_session_version_non_negative CHECK (session_version >= 0)
);

-- Catalogo de directores referenciados por las peliculas.
CREATE TABLE directors (
    director_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    ciudad VARCHAR(100)
);

-- Catalogo de actores que se relacionan con peliculas mediante film_actors.
CREATE TABLE actors (
    actor_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    ciudad VARCHAR(100)
);

-- Peliculas disponibles, su precio actual, existencias y director.
CREATE TABLE films (
    film_id SERIAL PRIMARY KEY,
    title VARCHAR(100) NOT NULL,
    release_year INT,
    price DECIMAL(10, 2) NOT NULL,
    stock INT NOT NULL DEFAULT 0,
    director_id INT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT films_director_fk
        FOREIGN KEY (director_id)
        REFERENCES directors(director_id)
        ON DELETE SET NULL,
    CONSTRAINT films_year_valid CHECK (
        release_year IS NULL OR release_year BETWEEN 1888 AND 9999
    ),
    CONSTRAINT films_price_non_negative CHECK (price >= 0),
    CONSTRAINT films_stock_non_negative CHECK (stock >= 0)
);

-- Pedidos de los usuarios. Un carrito pasa de open a paid o cancelled.
CREATE TABLE carts (
    cart_id SERIAL PRIMARY KEY,
    user_id INT NOT NULL,
    total_price DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    paid_at TIMESTAMPTZ,

    CONSTRAINT carts_user_fk
        FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE RESTRICT,
    CONSTRAINT carts_total_non_negative CHECK (total_price >= 0),
    CONSTRAINT carts_status_valid CHECK (status IN ('open', 'paid', 'cancelled')),
    CONSTRAINT carts_paid_at_valid CHECK (
        (status = 'paid' AND paid_at IS NOT NULL)
        OR (status <> 'paid' AND paid_at IS NULL)
    )
);

-- Garantiza en la propia base de datos que cada usuario solo tenga un carrito abierto.
CREATE UNIQUE INDEX one_open_cart_per_user
    ON carts (user_id)
    WHERE status = 'open';

-- Votos de 0 a 10. La restriccion UNIQUE permite un unico voto por usuario y pelicula.
CREATE TABLE ratings (
    rating_id SERIAL PRIMARY KEY,
    user_id INT NOT NULL,
    film_id INT NOT NULL,
    rating INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ratings_user_fk
        FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE RESTRICT,
    CONSTRAINT ratings_film_fk
        FOREIGN KEY (film_id)
        REFERENCES films(film_id)
        ON DELETE RESTRICT,
    CONSTRAINT one_rating_per_user_and_film UNIQUE (user_id, film_id),
    CONSTRAINT ratings_value_valid CHECK (rating BETWEEN 0 AND 10)
);

-- Lineas del carrito. unit_price conserva el precio que tenia la pelicula al añadirla.
CREATE TABLE cart_films (
    cart_id INT NOT NULL,
    film_id INT NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    unit_price DECIMAL(10, 2) NOT NULL,

    CONSTRAINT cart_films_pk PRIMARY KEY (cart_id, film_id),
    CONSTRAINT cart_films_cart_fk
        FOREIGN KEY (cart_id)
        REFERENCES carts(cart_id)
        ON DELETE CASCADE,
    CONSTRAINT cart_films_film_fk
        FOREIGN KEY (film_id)
        REFERENCES films(film_id)
        ON DELETE RESTRICT,
    CONSTRAINT cart_films_quantity_positive CHECK (quantity > 0),
    CONSTRAINT cart_films_price_non_negative CHECK (unit_price >= 0)
);

-- Relacion muchos a muchos entre peliculas y actores, incluido el personaje interpretado.
CREATE TABLE film_actors (
    film_id INT NOT NULL,
    actor_id INT NOT NULL,
    character_name VARCHAR(100),

    CONSTRAINT film_actors_pk PRIMARY KEY (film_id, actor_id),
    CONSTRAINT film_actors_film_fk
        FOREIGN KEY (film_id)
        REFERENCES films(film_id)
        ON DELETE CASCADE,
    CONSTRAINT film_actors_actor_fk
        FOREIGN KEY (actor_id)
        REFERENCES actors(actor_id)
        ON DELETE CASCADE
);

-- Reserva o devuelve stock cuando cambia el contenido de un carrito abierto.
CREATE OR REPLACE FUNCTION manage_cart_film_stock()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    selected_cart_id INT;
    cart_status VARCHAR(20);
    quantity_difference INT;
BEGIN
    selected_cart_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.cart_id ELSE NEW.cart_id END;

    SELECT status
    INTO cart_status
    FROM carts
    WHERE cart_id = selected_cart_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Cart % does not exist', selected_cart_id;
    END IF;

    IF cart_status <> 'open' THEN
        RAISE EXCEPTION 'Cart % is not open', selected_cart_id;
    END IF;

    IF TG_OP = 'INSERT' THEN
        UPDATE films
        SET stock = stock - NEW.quantity
        WHERE film_id = NEW.film_id
          AND active = TRUE
          AND stock >= NEW.quantity
        RETURNING price INTO NEW.unit_price;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Film % does not exist, is inactive, or has insufficient stock', NEW.film_id;
        END IF;

        RETURN NEW;
    END IF;

    IF TG_OP = 'DELETE' THEN
        UPDATE films
        SET stock = stock + OLD.quantity
        WHERE film_id = OLD.film_id;

        RETURN OLD;
    END IF;

    IF NEW.cart_id <> OLD.cart_id OR NEW.film_id <> OLD.film_id THEN
        RAISE EXCEPTION 'The cart and film identifiers cannot be changed';
    END IF;

    quantity_difference := NEW.quantity - OLD.quantity;
    NEW.unit_price := OLD.unit_price;

    IF quantity_difference > 0 THEN
        UPDATE films
        SET stock = stock - quantity_difference
        WHERE film_id = NEW.film_id
          AND active = TRUE
          AND stock >= quantity_difference;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Film % has insufficient stock', NEW.film_id;
        END IF;
    ELSIF quantity_difference < 0 THEN
        UPDATE films
        SET stock = stock + ABS(quantity_difference)
        WHERE film_id = NEW.film_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER manage_stock_before_cart_film_change
-- BEFORE permite rechazar la operacion o ajustar NEW.unit_price antes de guardar la fila.
BEFORE INSERT OR UPDATE OR DELETE ON cart_films
FOR EACH ROW
EXECUTE FUNCTION manage_cart_film_stock();

-- Mantiene el precio total después de cualquier cambio en el carrito.
CREATE OR REPLACE FUNCTION recalculate_cart_total()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    selected_cart_id INT;
BEGIN
    selected_cart_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.cart_id ELSE NEW.cart_id END;

    UPDATE carts
    SET total_price = COALESCE(
        (
            SELECT SUM(quantity * unit_price)
            FROM cart_films
            WHERE cart_id = selected_cart_id
        ),
        0.00
    )
    WHERE cart_id = selected_cart_id;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER recalculate_total_after_cart_film_change
-- AFTER calcula el total usando ya el contenido definitivo de cart_films.
AFTER INSERT OR UPDATE OR DELETE ON cart_films
FOR EACH ROW
EXECUTE FUNCTION recalculate_cart_total();

-- Descuenta el saldo y registra la fecha exactamente al pagar el carrito.
CREATE OR REPLACE FUNCTION handle_cart_status_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
        RETURN NEW;
    END IF;

    IF OLD.status IN ('paid', 'cancelled') THEN
        RAISE EXCEPTION 'Cart % is already % and cannot change status', OLD.cart_id, OLD.status;
    END IF;

    IF NEW.status = 'paid' THEN
        IF NEW.total_price <= 0 THEN
            RAISE EXCEPTION 'Cart % is empty', NEW.cart_id;
        END IF;

        UPDATE users
        SET money = money - NEW.total_price
        WHERE user_id = NEW.user_id
          AND active = TRUE
          AND money >= NEW.total_price;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'User % does not exist, is inactive, or has insufficient balance', NEW.user_id;
        END IF;

        NEW.paid_at := CURRENT_TIMESTAMP;
    ELSIF NEW.status = 'cancelled' THEN
        IF EXISTS (SELECT 1 FROM cart_films WHERE cart_id = NEW.cart_id) THEN
            RAISE EXCEPTION 'Remove the films before cancelling cart %', NEW.cart_id;
        END IF;
        NEW.paid_at := NULL;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER process_cart_status_before_update
BEFORE UPDATE OF status ON carts
FOR EACH ROW
EXECUTE FUNCTION handle_cart_status_change();

-- Devuelve el carrito abierto o crea uno para un usuario activo.
CREATE OR REPLACE FUNCTION get_or_create_open_cart(selected_user_id INT)
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    selected_cart_id INT;
BEGIN
    PERFORM 1
    FROM users
    WHERE user_id = selected_user_id
      AND active = TRUE
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'User % does not exist or is inactive', selected_user_id;
    END IF;

    SELECT cart_id
    INTO selected_cart_id
    FROM carts
    WHERE user_id = selected_user_id
      AND status = 'open';

    IF selected_cart_id IS NULL THEN
        INSERT INTO carts (user_id)
        VALUES (selected_user_id)
        RETURNING cart_id INTO selected_cart_id;
    END IF;

    RETURN selected_cart_id;
END;
$$;

-- Añade unidades al carrito; los triggers reservan stock y recalculan el total.
CREATE OR REPLACE FUNCTION add_film_to_cart(
    selected_cart_id INT,
    selected_film_id INT,
    selected_quantity INT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    IF selected_quantity <= 0 THEN
        RAISE EXCEPTION 'Quantity must be greater than zero';
    END IF;

    UPDATE cart_films
    SET quantity = quantity + selected_quantity
    WHERE cart_id = selected_cart_id
      AND film_id = selected_film_id;

    IF NOT FOUND THEN
        INSERT INTO cart_films (cart_id, film_id, quantity, unit_price)
        VALUES (selected_cart_id, selected_film_id, selected_quantity, 0.00);
    END IF;
END;
$$;

-- Quita completamente una pelicula del carrito; el trigger devuelve su stock.
CREATE OR REPLACE FUNCTION remove_film_from_cart(
    selected_cart_id INT,
    selected_film_id INT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM cart_films
    WHERE cart_id = selected_cart_id
      AND film_id = selected_film_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Film % is not in cart %', selected_film_id, selected_cart_id;
    END IF;
END;
$$;

-- El trigger de carts efectúa el cobro y completa paid_at.
CREATE OR REPLACE FUNCTION pay_open_cart(selected_cart_id INT)
RETURNS TABLE (
    paid_cart_id INT,
    paid_total DECIMAL(10, 2),
    payment_date TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    UPDATE carts
    SET status = 'paid'
    WHERE cart_id = selected_cart_id
      AND status = 'open'
    RETURNING cart_id, total_price, paid_at;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Open cart % does not exist', selected_cart_id;
    END IF;
END;
$$;

-- Vacia y cancela un carrito abierto. Al borrar sus lineas se devuelve el stock.
CREATE OR REPLACE FUNCTION cancel_open_cart(selected_cart_id INT)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    selected_status VARCHAR(20);
BEGIN
    SELECT status
    INTO selected_status
    FROM carts
    WHERE cart_id = selected_cart_id
    FOR UPDATE;

    IF NOT FOUND OR selected_status <> 'open' THEN
        RAISE EXCEPTION 'Open cart % does not exist', selected_cart_id;
    END IF;

    DELETE FROM cart_films WHERE cart_id = selected_cart_id;
    UPDATE carts SET status = 'cancelled' WHERE cart_id = selected_cart_id;
END;
$$;

-- Calcula la media de votos; devuelve 0 cuando la pelicula aun no tiene votos.
CREATE OR REPLACE FUNCTION average_film_rating(selected_film_id INT)
RETURNS DECIMAL(4, 2)
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(AVG(rating), 0)::DECIMAL(4, 2)
    FROM ratings
    WHERE film_id = selected_film_id;
$$;

-- Informe requerido por /ventas/<año>/<pais>. Devuelve una fila por pelicula vendida.
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
      AND EXTRACT(YEAR FROM c.paid_at)::INT = selected_year
      AND LOWER(u.country) = LOWER(selected_country)
    ORDER BY c.paid_at, c.cart_id, f.film_id;
$$;

-- Hace permanentes conjuntamente las tablas, restricciones, funciones y triggers.
COMMIT;
