-- Очистка таблиц (опционально)
TRUNCATE TABLE 
    reviews,
    payments,
    rentals,
    bikes,
    stations,
    bike_types,
    users 
RESTART IDENTITY;

-- Тестовые пользователи (Telegram ID)
INSERT INTO users (user_id, full_name, username, phone, role) VALUES
(123456789, 'Иван Петров', 'ivan_petrov', '+79161234567', 'client'),
(987654321, 'Мария Сидорова', 'maria_sid', '+79031112233', 'client'),
(555555555, 'Админ Админович', 'admin_bot', NULL, 'admin');

-- Типы велосипедов
INSERT INTO bike_types (name, description, price_per_hour) VALUES
('Городской', 'Удобный для города, с корзиной', 150),
('Горный', 'Проходимый с амортизацией', 200),
('Шоссейный', 'Легкий для скоростной езды', 250);

-- Станции
INSERT INTO stations (name, address, capacity, latitude, longitude) VALUES
('Центральная', 'ул. Пушкина, 1', 20, 55.751244, 37.618423),
('Вокзальная', 'пл. Ленина, 5', 15, 55.732101, 37.658359),
('Парковая', 'ул. Садовая, 10', 30, 55.761690, 37.608702);

-- Велосипеды
INSERT INTO bikes (type_id, station_id, status, purchase_date) VALUES
(1, 1, 'available', '2023-01-10'),
(2, 1, 'available', '2023-02-15'),
(3, 2, 'rented', '2023-03-20'),
(1, 3, 'under_maintenance', '2023-04-25'),
(2, 3, 'available', '2023-05-01');

-- Аренды
INSERT INTO rentals (user_id, bike_id, start_time, end_time, start_station_id, end_station_id) VALUES
(123456789, 3, '2024-01-10 14:00:00', '2024-01-10 16:30:00', 2, 1),
(987654321, 1, '2024-01-11 09:15:00', NULL, 1, NULL),
(123456789, 2, '2024-01-12 10:00:00', '2024-01-12 12:00:00', 1, 3);

-- Платежи
INSERT INTO payments (rental_id, amount, status) VALUES
(1, 375.00, 'completed'), -- 2.5 часа * 150 руб
(3, 400.00, 'completed'); -- 2 часа * 200 руб

-- Отзывы
INSERT INTO reviews (user_id, bike_id, rating, comment) VALUES
(123456789, 3, 5, 'Отличный велосипед!'),
(987654321, 1, 4, 'Удобно, но тяжеловат'),
(123456789, 2, 5, 'Идеален для бездорожья');