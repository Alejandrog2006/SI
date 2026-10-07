
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    country VARCHAR(100) NOT NULL,
    money DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    role VARCHAR(20) NOT NULL DEFAULT 'user',

    CHECK (money >= 0),
    CHECK (role IN ('user', 'admin'))
);


CREATE TABLE directors (
    director_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    ciudad VARCHAR(100)
);


CREATE TABLE actors (
    actor_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    ciudad VARCHAR(100)
);


CREATE TABLE films (
    film_id SERIAL PRIMARY KEY,
    title VARCHAR(100) NOT NULL,
    release_year INT,
    price DECIMAL(10, 2) NOT NULL,
    stock INT NOT NULL DEFAULT 0,
    director_id INT,

    FOREIGN KEY (director_id)
        REFERENCES directors(director_id)
        ON DELETE SET NULL,

    CHECK (price >= 0),
    CHECK (stock >= 0)
);


CREATE TABLE carts (
    cart_id SERIAL PRIMARY KEY,
    user_id INT NOT NULL,
    total_price DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    CHECK (total_price >= 0),
    CHECK (status IN ('open', 'paid', 'cancelled'))
);


CREATE TABLE ratings (
    rating_id SERIAL PRIMARY KEY,
    user_id INT NOT NULL,
    film_id INT NOT NULL,
    rating INT NOT NULL,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    FOREIGN KEY (film_id)
        REFERENCES films(film_id)
        ON DELETE CASCADE,

    UNIQUE (user_id, film_id),
    CHECK (rating >= 0 AND rating <= 10)
);


CREATE TABLE cart_films (
    cart_id INT NOT NULL,
    film_id INT NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    unit_price DECIMAL(10, 2) NOT NULL,

    PRIMARY KEY (cart_id, film_id),

    FOREIGN KEY (cart_id)
        REFERENCES carts(cart_id)
        ON DELETE CASCADE,

    FOREIGN KEY (film_id)
        REFERENCES films(film_id),

    CHECK (quantity > 0),
    CHECK (unit_price >= 0)
);


CREATE TABLE film_actors (
    film_id INT NOT NULL,
    actor_id INT NOT NULL,

    PRIMARY KEY (film_id, actor_id),

    FOREIGN KEY (film_id)
        REFERENCES films(film_id)
        ON DELETE CASCADE,

    FOREIGN KEY (actor_id)
        REFERENCES actors(actor_id)
        ON DELETE CASCADE
);


1. Al insertar o aumentar un elemento del carrito se comprueba y reserva el stock.

CREATE OR REPLACE FUNCTION reserve_film_stock(cart_id INT) RETURNS TRIGGER 
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE films
    SET stock = stock - NEW.quantity
    WHERE film_id = NEW.film_id;
        AND stock >= NEW.quantity;
    RETURNING PRICE INTO NEW.unit_price;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Not enough stock for film_id %', NEW.film_id;
    END IF;

    RETURN NEW;
END;
$$;

2. Al eliminar o reducir un elemento se devuelve la diferencia al stock.
 
CREATE OR REPLACE FUNCTION release_film_stock(cart_id INT) RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE films
    SET stock = stock + OLD.quantity
    WHERE film_id = OLD.film_id;

    RETURN OLD;
END;
$$;

3. Después de modificar los elementos se recalcula el total del carrito.
CREATE OR REPLACE FUNCTION update_cart_total(cart_id INT) RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE carts
    SET total_price = (
        SELECT COALESCE(
            SUM(quantity * unit_price),
            0
        )
        FROM cart_films
        WHERE cart_id = NEW.cart_id
    )
    WHERE cart_id = NEW.cart_id;

    RETURN NEW;
END;
$$;

4. Al cambiar un carrito de `open` a `paid` se comprueba el saldo, se descuenta el total y se asigna `paid_at`.
CREATE OR REPLACE FUNCTION pay_cart(cart_id INT) RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN   
    IF NEW.status = 'paid' THEN
        UPDATE users
        SET money = money - NEW.total_price
        WHERE user_id = (SELECT user_id FROM carts WHERE cart_id = NEW.cart_id)
            AND money >= NEW.total_price;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Not enough balance to pay for cart_id %', NEW.cart_id;
        END IF;

    END IF;

    RETURN NEW;
END;
$$;

5. No se permite modificar un carrito que ya esté pagado o cancelado.
CREATE OR REPLACE FUNCTION prevent_cart_modification() RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status IN ('paid', 'cancelled') THEN
        RAISE EXCEPTION 'Cannot modify a cart that is already paid or cancelled';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER reserve_stock_before_insert
BEFORE INSERT ON cart_films
FOR EACH ROW
EXECUTE FUNCTION reserve_film_stock();

CREATE TRIGGER release_stock_after_delete
AFTER DELETE ON cart_films
FOR EACH ROW
EXECUTE FUNCTION release_film_stock();

CREATE TRIGGER restore_stock_after_delete
AFTER DELETE ON cart_films
FOR EACH ROW
EXECUTE FUNCTION restore_film_stock();

CREATE TRIGGER update_total_after_insert
AFTER INSERT ON cart_films
FOR EACH ROW
EXECUTE FUNCTION update_cart_total();