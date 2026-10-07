INSERT INTO users (username, password_hash, country, money, role)
VALUES
	('ana', '$2b$12$abcdefghijklmnopqrstuu7i7h5Q2Qv1v6v8hP8Q6QqQqQqQqQq', 'España', 120.00, 'user'),
	('bruno', '$2b$12$abcdefghijklmnopqrstuu7i7h5Q2Qv1v6v8hP8Q6QqQqQqQqQq', 'Francia', 80.00, 'user'),
	('admin', '$2b$12$abcdefghijklmnopqrstuu7i7h5Q2Qv1v6v8hP8Q6QqQqQqQqQq', 'España', 0.00, 'admin');

INSERT INTO directors (name, ciudad)
VALUES
	('Christopher Nolan', 'Londres'),
	('Greta Gerwig', 'Sacramento'),
	('Pedro Almodóvar', 'Calzada de Calatrava');

INSERT INTO actors (name, ciudad)
VALUES
	('Leonardo DiCaprio', 'Los Ángeles'),
	('Margot Robbie', 'Dalby'),
	('Cillian Murphy', 'Douglas'),
	('Ryan Gosling', 'London'),
	('Penélope Cruz', 'Alcobendas');

INSERT INTO films (title, release_year, price, stock, director_id)
VALUES
	('Origen', 2010, 12.99, 8, (SELECT director_id FROM directors WHERE name = 'Christopher Nolan')),
	('Barbie', 2023, 10.99, 10, (SELECT director_id FROM directors WHERE name = 'Greta Gerwig')),
	('Oppenheimer', 2023, 14.99, 6, (SELECT director_id FROM directors WHERE name = 'Christopher Nolan')),
	('Volver', 2006, 8.99, 5, (SELECT director_id FROM directors WHERE name = 'Pedro Almodóvar'));

INSERT INTO film_actors (film_id, actor_id)
VALUES
	((SELECT film_id FROM films WHERE title = 'Origen'), (SELECT actor_id FROM actors WHERE name = 'Leonardo DiCaprio')),
	((SELECT film_id FROM films WHERE title = 'Origen'), (SELECT actor_id FROM actors WHERE name = 'Cillian Murphy')),
	((SELECT film_id FROM films WHERE title = 'Barbie'), (SELECT actor_id FROM actors WHERE name = 'Margot Robbie')),
	((SELECT film_id FROM films WHERE title = 'Barbie'), (SELECT actor_id FROM actors WHERE name = 'Ryan Gosling')),
	((SELECT film_id FROM films WHERE title = 'Oppenheimer'), (SELECT actor_id FROM actors WHERE name = 'Cillian Murphy')),
	((SELECT film_id FROM films WHERE title = 'Volver'), (SELECT actor_id FROM actors WHERE name = 'Penélope Cruz'));

INSERT INTO ratings (user_id, film_id, rating)
VALUES
	((SELECT user_id FROM users WHERE username = 'ana'), (SELECT film_id FROM films WHERE title = 'Origen'), 9),
	((SELECT user_id FROM users WHERE username = 'bruno'), (SELECT film_id FROM films WHERE title = 'Origen'), 8),
	((SELECT user_id FROM users WHERE username = 'ana'), (SELECT film_id FROM films WHERE title = 'Barbie'), 7),
	((SELECT user_id FROM users WHERE username = 'bruno'), (SELECT film_id FROM films WHERE title = 'Oppenheimer'), 10);

-- Pruebas de funcionamiento de los triggers y funciones

DO $$
DECLARE
	ana_cart_id INT;
	bruno_cart_id INT;
BEGIN
	ana_cart_id := get_or_create_open_cart((SELECT user_id FROM users WHERE username = 'ana'));
	PERFORM add_film_to_cart(ana_cart_id, (SELECT film_id FROM films WHERE title = 'Origen'), 1);
	PERFORM add_film_to_cart(ana_cart_id, (SELECT film_id FROM films WHERE title = 'Barbie'), 2);

	bruno_cart_id := get_or_create_open_cart((SELECT user_id FROM users WHERE username = 'bruno'));
	PERFORM add_film_to_cart(bruno_cart_id, (SELECT film_id FROM films WHERE title = 'Oppenheimer'), 1);
	PERFORM pay_open_cart(bruno_cart_id);
END;
$$;
