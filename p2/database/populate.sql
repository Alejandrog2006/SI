-- Inserta datos reproducibles para probar usuarios, catalogo, carritos y ventas.
-- La transaccion evita que la base quede cargada solo parcialmente si algo falla.
BEGIN;

-- Contraseñas de prueba: ana1234, bruno1234 y admin1234 (SHA-256).
INSERT INTO users (username, password_hash, country, money, role)
VALUES
    ('ana', 'c1ea922bc882d3586346a63d47660230731014e9fc52e3641aee8ec0123c20e4', 'España', 120.00, 'user'),
    ('bruno', '80fdc972f9021d45e7c95c08272a841f80dca992253c39ee600e3dfea952ae80', 'Francia', 80.00, 'user'),
    ('admin', 'ac9689e2272427085e35b9d3e3e8bed88cb3434828b43b86fc0596cad4c6e270', 'España', 0.00, 'admin');

-- Directores de ejemplo referenciados posteriormente por las peliculas.
INSERT INTO directors (name, ciudad)
VALUES
    ('Christopher Nolan', 'Londres'),
    ('Greta Gerwig', 'Sacramento'),
    ('Pedro Almodóvar', 'Calzada de Calatrava');

-- Actores de ejemplo para probar la relacion muchos a muchos.
INSERT INTO actors (name, ciudad)
VALUES
    ('Leonardo DiCaprio', 'Los Ángeles'),
    ('Margot Robbie', 'Dalby'),
    ('Cillian Murphy', 'Douglas'),
    ('Ryan Gosling', 'Londres'),
    ('Penélope Cruz', 'Alcobendas');

-- Catalogo inicial. Las subconsultas evitan depender de valores SERIAL concretos.
INSERT INTO films (title, release_year, price, stock, director_id)
VALUES
    ('Origen', 2010, 12.99, 8, (SELECT director_id FROM directors WHERE name = 'Christopher Nolan')),
    ('Barbie', 2023, 10.99, 10, (SELECT director_id FROM directors WHERE name = 'Greta Gerwig')),
    ('Oppenheimer', 2023, 14.99, 6, (SELECT director_id FROM directors WHERE name = 'Christopher Nolan')),
    ('Volver', 2006, 8.99, 5, (SELECT director_id FROM directors WHERE name = 'Pedro Almodóvar'));

-- Reparto de cada pelicula y nombre del personaje interpretado.
INSERT INTO film_actors (film_id, actor_id, character_name)
VALUES
    ((SELECT film_id FROM films WHERE title = 'Origen'), (SELECT actor_id FROM actors WHERE name = 'Leonardo DiCaprio'), 'Cobb'),
    ((SELECT film_id FROM films WHERE title = 'Origen'), (SELECT actor_id FROM actors WHERE name = 'Cillian Murphy'), 'Robert Fischer'),
    ((SELECT film_id FROM films WHERE title = 'Barbie'), (SELECT actor_id FROM actors WHERE name = 'Margot Robbie'), 'Barbie'),
    ((SELECT film_id FROM films WHERE title = 'Barbie'), (SELECT actor_id FROM actors WHERE name = 'Ryan Gosling'), 'Ken'),
    ((SELECT film_id FROM films WHERE title = 'Oppenheimer'), (SELECT actor_id FROM actors WHERE name = 'Cillian Murphy'), 'J. Robert Oppenheimer'),
    ((SELECT film_id FROM films WHERE title = 'Volver'), (SELECT actor_id FROM actors WHERE name = 'Penélope Cruz'), 'Raimunda');

-- Votos iniciales utilizados para comprobar el calculo de la puntuacion media.
INSERT INTO ratings (user_id, film_id, rating)
VALUES
    ((SELECT user_id FROM users WHERE username = 'ana'), (SELECT film_id FROM films WHERE title = 'Origen'), 9),
    ((SELECT user_id FROM users WHERE username = 'bruno'), (SELECT film_id FROM films WHERE title = 'Origen'), 8),
    ((SELECT user_id FROM users WHERE username = 'ana'), (SELECT film_id FROM films WHERE title = 'Barbie'), 7),
    ((SELECT user_id FROM users WHERE username = 'bruno'), (SELECT film_id FROM films WHERE title = 'Oppenheimer'), 10);

-- Crea un carrito abierto para Ana y una venta pagada para Bruno.
-- El bloque anonimo permite guardar los identificadores de los carritos en variables.
DO $$
DECLARE
    ana_cart_id INT;
    bruno_cart_id INT;
BEGIN
    -- Ana conserva un carrito abierto con tres unidades en total.
    ana_cart_id := get_or_create_open_cart(
        (SELECT user_id FROM users WHERE username = 'ana')
    );
    PERFORM add_film_to_cart(
        ana_cart_id,
        (SELECT film_id FROM films WHERE title = 'Origen'),
        1
    );
    PERFORM add_film_to_cart(
        ana_cart_id,
        (SELECT film_id FROM films WHERE title = 'Barbie'),
        2
    );

    -- Bruno completa una compra para disponer de datos en el informe de ventas.
    bruno_cart_id := get_or_create_open_cart(
        (SELECT user_id FROM users WHERE username = 'bruno')
    );
    PERFORM add_film_to_cart(
        bruno_cart_id,
        (SELECT film_id FROM films WHERE title = 'Oppenheimer'),
        1
    );
    PERFORM pay_open_cart(bruno_cart_id);
END;
$$;

-- Confirma conjuntamente todos los datos de demostracion.
COMMIT;
