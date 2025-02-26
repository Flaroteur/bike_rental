-- ----------------------------
-- 1. Создание таблиц (Tables)
-- ----------------------------

CREATE TABLE bike_types (
    type_id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    price_per_hour NUMERIC(8, 2) CHECK (price_per_hour > 0)
);

CREATE TABLE stations (
    station_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    address TEXT NOT NULL,
    capacity INT CHECK (capacity > 0),
    latitude NUMERIC(10, 6),
    longitude NUMERIC(10, 6)
);

CREATE TABLE users (
    user_id BIGINT PRIMARY KEY, 
    full_name VARCHAR(100) NOT NULL,
    username VARCHAR(100),
    registration_date TIMESTAMP DEFAULT NOW(),
    phone VARCHAR(20) UNIQUE,
    password_hash VARCHAR(128),
    role VARCHAR(20) CHECK (role IN ('client', 'admin'))
);

CREATE TABLE bikes (
    bike_id SERIAL PRIMARY KEY,
    type_id INT REFERENCES bike_types(type_id) ON DELETE SET NULL,
    station_id INT REFERENCES stations(station_id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('available', 'rented', 'under_maintenance')),
    purchase_date DATE NOT NULL
);

CREATE TABLE rentals (
    rental_id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    bike_id INT REFERENCES bikes(bike_id) ON DELETE CASCADE,
    start_time TIMESTAMP NOT NULL DEFAULT NOW(),
    end_time TIMESTAMP,
    start_station_id INT REFERENCES stations(station_id) ON DELETE SET NULL,
    end_station_id INT REFERENCES stations(station_id) ON DELETE SET NULL
);

CREATE TABLE payments (
    payment_id SERIAL PRIMARY KEY,
    rental_id INT REFERENCES rentals(rental_id) ON DELETE CASCADE,
    amount NUMERIC(10, 2) CHECK (amount > 0),
    payment_date TIMESTAMP DEFAULT NOW(),
    status VARCHAR(20) CHECK (status IN ('pending', 'completed', 'failed'))
);

CREATE TABLE reviews (
    review_id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    bike_id INT REFERENCES bikes(bike_id) ON DELETE CASCADE,
    rating INT CHECK (rating BETWEEN 1 AND 5),
    comment TEXT,
    review_date TIMESTAMP DEFAULT NOW()
);

-- ----------------------------
-- 2. Индексы (Indexes)
-- ----------------------------

CREATE INDEX idx_bikes_status ON bikes(status);
CREATE INDEX idx_rentals_user_id ON rentals(user_id);
CREATE INDEX idx_rentals_bike_id ON rentals(bike_id);

-- ----------------------------
-- 3. Триггеры и функции (Triggers & Functions)
-- ----------------------------

CREATE OR REPLACE FUNCTION set_bike_rented()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE bikes
    SET status = 'rented', station_id = NULL
    WHERE bike_id = NEW.bike_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_rental_start
AFTER INSERT ON rentals
FOR EACH ROW
EXECUTE FUNCTION set_bike_rented();


-- Триггер для обновления статуса при завершении аренды
CREATE OR REPLACE FUNCTION update_bike_on_rental_end()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.end_time IS NOT NULL THEN
        UPDATE bikes 
        SET 
            status = 'available',
            station_id = NEW.end_station_id
        WHERE bike_id = NEW.bike_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_rental_end
AFTER UPDATE ON rentals
FOR EACH ROW
WHEN (OLD.end_time IS DISTINCT FROM NEW.end_time)
EXECUTE FUNCTION update_bike_on_rental_end();
-- ----------------------------
-- 4. Хранимые процедуры (Stored Procedures)
-- ----------------------------

CREATE OR REPLACE PROCEDURE close_rental(
    IN rental_id INT,
    IN end_station_id INT
)
LANGUAGE plpgsql
AS $$
DECLARE
    rental_cost NUMERIC;
BEGIN
    UPDATE rentals
    SET 
        end_time = NOW(),
        end_station_id = end_station_id
    WHERE rentals.rental_id = close_rental.rental_id;

    SELECT (EXTRACT(EPOCH FROM (end_time - start_time)/3600) * bt.price_per_hour)
    INTO rental_cost
    FROM rentals r
    JOIN bikes b ON r.bike_id = b.bike_id
    JOIN bike_types bt ON b.type_id = bt.type_id
    WHERE r.rental_id = close_rental.rental_id;

    INSERT INTO payments (rental_id, amount, status)
    VALUES (rental_id, rental_cost, 'completed');
END;
$$;

-- ----------------------------
-- 5. Представления (Views)
-- ----------------------------

CREATE OR REPLACE VIEW active_rentals AS
SELECT 
    r.rental_id, 
    u.full_name AS user_name, 
    b.bike_id, 
    s.name AS start_station,
    r.start_time
FROM rentals r
JOIN users u ON r.user_id = u.user_id
JOIN bikes b ON r.bike_id = b.bike_id
JOIN stations s ON r.start_station_id = s.station_id
WHERE r.end_time IS NULL;