
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


CREATE OR REPLACE FUNCTION check_cart_is_open()
RETURNS TRIGGER AS $$
DECLARE
    cart_status VARCHAR(20);
BEGIN
    SELECT status INTO cart_status
    FROM carts
    WHERE cart_id = COALESCE(NEW.cart_id, OLD.cart_id)
    FOR UPDATE;

    IF cart_status <> 'open' THEN
        RAISE EXCEPTION 'Cart % is not open', COALESCE(NEW.cart_id, OLD.cart_id);
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;

    IF TG_OP = 'UPDATE' AND (NEW.cart_id <> OLD.cart_id OR NEW.film_id <> OLD.film_id) THEN
        RAISE EXCEPTION 'Cart and film identifiers cannot be changed';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION reserve_cart_stock()
RETURNS TRIGGER AS $$
DECLARE
    stock_difference INT;
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE films SET stock = stock - NEW.quantity
        WHERE film_id = NEW.film_id AND stock >= NEW.quantity;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Insufficient stock for film %', NEW.film_id;
        END IF;
    ELSIF TG_OP = 'UPDATE' THEN
        stock_difference := NEW.quantity - OLD.quantity;
        IF stock_difference > 0 THEN
            UPDATE films SET stock = stock - stock_difference
            WHERE film_id = NEW.film_id AND stock >= stock_difference;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Insufficient stock for film %', NEW.film_id;
            END IF;
        ELSIF stock_difference < 0 THEN
            UPDATE films SET stock = stock - stock_difference
            WHERE film_id = OLD.film_id;
        END IF;
    ELSE
        UPDATE films SET stock = stock + OLD.quantity
        WHERE film_id = OLD.film_id;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION refresh_cart_total()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE carts
    SET total_price = COALESCE(
        (SELECT SUM(quantity * unit_price) FROM cart_films
         WHERE cart_id = COALESCE(NEW.cart_id, OLD.cart_id)), 0.00)
    WHERE cart_id = COALESCE(NEW.cart_id, OLD.cart_id);

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pay_cart()
RETURNS TRIGGER AS $$
DECLARE
    current_money DECIMAL(10, 2);
BEGIN
    IF OLD.status <> 'open' OR NEW.status <> 'paid' THEN
        RAISE EXCEPTION 'Only an open cart can be paid';
    END IF;

    SELECT money INTO current_money FROM users
    WHERE user_id = NEW.user_id FOR UPDATE;
    IF current_money < NEW.total_price THEN
        RAISE EXCEPTION 'Insufficient balance for user %', NEW.user_id;
    END IF;

    UPDATE users SET money = money - NEW.total_price
    WHERE user_id = NEW.user_id;
    NEW.paid_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION prevent_closed_cart_changes()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status <> 'open' THEN
        RAISE EXCEPTION 'Cart % cannot be modified after it is closed', OLD.cart_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION average_film_rating(target_film_id INT)
RETURNS DECIMAL(4, 2) AS $$
    SELECT COALESCE(AVG(rating), 0.00)::DECIMAL(4, 2)
    FROM ratings WHERE film_id = target_film_id;
$$ LANGUAGE SQL STABLE;

CREATE OR REPLACE FUNCTION get_or_create_open_cart(target_user_id INT)
RETURNS INT AS $$
DECLARE
    open_cart_id INT;
BEGIN
    SELECT cart_id INTO open_cart_id FROM carts
    WHERE user_id = target_user_id AND status = 'open'
    ORDER BY cart_id LIMIT 1 FOR UPDATE;
    IF open_cart_id IS NULL THEN
        INSERT INTO carts (user_id) VALUES (target_user_id)
        RETURNING cart_id INTO open_cart_id;
    END IF;
    RETURN open_cart_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION add_film_to_cart(
    target_cart_id INT, target_film_id INT, amount INT DEFAULT 1
)
RETURNS VOID AS $$
DECLARE
    film_price DECIMAL(10, 2);
BEGIN
    IF amount <= 0 THEN
        RAISE EXCEPTION 'Quantity must be positive';
    END IF;
    SELECT price INTO film_price FROM films WHERE film_id = target_film_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Film % does not exist', target_film_id;
    END IF;
    INSERT INTO cart_films (cart_id, film_id, quantity, unit_price)
    VALUES (target_cart_id, target_film_id, amount, film_price)
    ON CONFLICT (cart_id, film_id)
    DO UPDATE SET quantity = cart_films.quantity + EXCLUDED.quantity;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pay_open_cart(target_cart_id INT)
RETURNS VOID AS $$
BEGIN
    UPDATE carts SET status = 'paid'
    WHERE cart_id = target_cart_id AND status = 'open';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Open cart % does not exist', target_cart_id;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER cart_films_check_open
BEFORE INSERT OR UPDATE OR DELETE ON cart_films
FOR EACH ROW EXECUTE FUNCTION check_cart_is_open();

CREATE TRIGGER cart_films_reserve_stock
BEFORE INSERT OR UPDATE OR DELETE ON cart_films
FOR EACH ROW EXECUTE FUNCTION reserve_cart_stock();

CREATE TRIGGER cart_films_refresh_total
AFTER INSERT OR UPDATE OR DELETE ON cart_films
FOR EACH ROW EXECUTE FUNCTION refresh_cart_total();

CREATE TRIGGER carts_pay
BEFORE UPDATE OF status ON carts
FOR EACH ROW WHEN (OLD.status = 'open' AND NEW.status = 'paid')
EXECUTE FUNCTION pay_cart();

CREATE TRIGGER carts_prevent_closed_changes
BEFORE UPDATE ON carts
FOR EACH ROW WHEN (OLD.status <> 'open')
EXECUTE FUNCTION prevent_closed_cart_changes();

CREATE UNIQUE INDEX carts_one_open_per_user
ON carts (user_id) WHERE status = 'open';