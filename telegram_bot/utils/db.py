import logging
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from config import DB_CONFIG, LOGGING_CONFIG

# Настройка логгера
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_CONFIG["level"])
handler = logging.FileHandler(LOGGING_CONFIG["file"])
handler.setFormatter(logging.Formatter(LOGGING_CONFIG["format"]))
logger.addHandler(handler)

class DatabaseError(Exception):
    """Кастомное исключение для ошибок БД"""
    pass

class DBManager:
    """Менеджер для работы с PostgreSQL"""
    
    def __init__(self):
        self.conn = None
        self.cursor = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def connect(self):
        """Установка соединения с БД"""
        try:
            self.conn = psycopg2.connect(**DB_CONFIG)
            self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
            logger.info("Connected to PostgreSQL")
        except psycopg2.OperationalError as e:
            logger.error(f"Connection error: {e}")
            raise DatabaseError("Database connection failed") from e

    def close(self):
        """Закрытие соединения"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
            logger.info("Connection closed")

    def execute(self, query, params=None, commit=False):
        """Выполнение SQL-запроса"""
        try:
            self.cursor.execute(query, params)
            if commit:
                self.conn.commit()
            logger.debug(f"Executed query: {query}")
            return self.cursor
        except psycopg2.Error as e:
            self.conn.rollback()
            logger.error(f"Query failed: {e}\nQuery: {query}")
            raise DatabaseError("Database operation failed") from e

    def fetch_one(self, query, params=None):
        """Получение одной записи"""
        self.execute(query, params)
        return self.cursor.fetchone()

    def fetch_all(self, query, params=None):
        """Получение всех записей"""
        self.execute(query, params)
        return self.cursor.fetchall()


def get_available_bikes(station_id=None):
    """Получение доступных велосипедов"""
    query = sql.SQL("""
        SELECT b.bike_id, bt.name as type, s.name as station, bt.price_per_hour
        FROM bikes b
        JOIN bike_types bt ON b.type_id = bt.type_id
        LEFT JOIN stations s ON b.station_id = s.station_id
        WHERE b.status = 'available'
    """)
    
    if station_id:
        query = query + sql.SQL(" AND b.station_id = %s")
    
    with DBManager() as db:
        return db.fetch_all(query, (station_id,)) if station_id else db.fetch_all(query)



# def close_rental(rental_id: int, end_station_id: int) -> bool:
#     """Завершение аренды"""
#     query = sql.SQL("CALL close_rental(%s, %s)")
    
#     try:
#         with DBManager() as db:
#             db.execute(query, (rental_id, end_station_id), commit=True)
#             return True
#     except Exception as e:
#         logger.error(f"Close rental error: {e}")
#         return False


def close_rental(rental_id: int, end_station_id: int) -> bool:
    """Завершение аренды и обновление статуса велосипеда"""
    try:
        # 1. Обновление записи аренды
        update_rental_query = sql.SQL("""
            UPDATE rentals 
            SET 
                end_time = NOW(),
                end_station_id = %s
            WHERE rental_id = %s
        """)
        
        # 2. Обновление статуса велосипеда
        update_bike_query = sql.SQL("""
            UPDATE bikes 
            SET 
                status = 'available',
                station_id = %s
            WHERE bike_id = (
                SELECT bike_id FROM rentals WHERE rental_id = %s
            )
        """)
        
        with DBManager() as db:
            # Выполняем в транзакции
            db.execute(update_rental_query, (end_station_id, rental_id), commit=False)
            db.execute(update_bike_query, (end_station_id, rental_id), commit=True)
            
        return True
    except Exception as e:
        logger.error(f"Close rental error: {e}")
        return False

def get_user_rentals(user_id: int) -> list[dict]:
    """Получение всех аренд пользователя с деталями"""
    query = sql.SQL("""
        SELECT 
            r.rental_id,
            r.start_time,
            r.end_time,
            s_start.name as start_station,
            s_end.name as end_station,
            b.bike_id,
            bt.name as bike_type
        FROM rentals r
        JOIN bikes b ON r.bike_id = b.bike_id
        JOIN bike_types bt ON b.type_id = bt.type_id
        LEFT JOIN stations s_start ON r.start_station_id = s_start.station_id
        LEFT JOIN stations s_end ON r.end_station_id = s_end.station_id
        WHERE r.user_id = %s
        ORDER BY r.start_time DESC
    """)
    with DBManager() as db:
        return db.fetch_all(query, (user_id,))

### Платежи ###
def create_payment(rental_id: int, amount: float, status: str = "pending") -> dict:
    """Создание записи о платеже"""
    query = sql.SQL("""
        INSERT INTO payments (rental_id, amount, status)
        VALUES (%s, %s, %s)
        RETURNING payment_id, payment_date
    """)
    
    with DBManager() as db:
        result = db.execute(query, (rental_id, amount, status), commit=True)
        return result.fetchone()

def get_payments_by_user(user_id: int) -> list:
    """Получение всех платежей пользователя"""
    query = sql.SQL("""
        SELECT p.* 
        FROM payments p
        JOIN rentals r ON p.rental_id = r.rental_id
        WHERE r.user_id = %s
        ORDER BY p.payment_date DESC
    """)
    
    with DBManager() as db:
        return db.fetch_all(query, (user_id,))

def update_payment_status(payment_id: int, new_status: str) -> bool:
    """Обновление статуса платежа"""
    allowed_statuses = ['pending', 'completed', 'failed']
    if new_status not in allowed_statuses:
        raise ValueError(f"Invalid status. Allowed: {allowed_statuses}")
    
    query = sql.SQL("""
        UPDATE payments
        SET status = %s
        WHERE payment_id = %s
    """)
    
    with DBManager() as db:
        db.execute(query, (new_status, payment_id), commit=True)
        return True

def calculate_total_income() -> float:
    """Общий доход системы (только завершенные платежи)"""
    query = sql.SQL("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM payments
        WHERE status = 'completed'
    """)
    
    with DBManager() as db:
        result = db.fetch_one(query)
        return result['total']

### Отзывы ###
def add_review(user_id: int, bike_id: int, rating: int, comment: str = None) -> bool:
    """Добавление отзыва"""
    query = sql.SQL("""
        INSERT INTO reviews (user_id, bike_id, rating, comment)
        VALUES (%s, %s, %s, %s)
    """)
    try:
        with DBManager() as db:
            db.execute(query, (user_id, bike_id, rating, comment), commit=True)
            return True
    except Exception as e:
        logger.error(f"Add review error: {e}")
        return False

def get_reviews_by_bike(bike_id: int) -> list:
    """Получение отзывов по велосипеду"""
    query = sql.SQL("""
        SELECT rating, comment 
        FROM reviews 
        WHERE bike_id = %s
    """)
    with DBManager() as db:
        return db.fetch_all(query, (bike_id,))

def get_average_rating(bike_id: int) -> float:
    """Средний рейтинг велосипеда"""
    query = sql.SQL("""
        SELECT ROUND(AVG(rating)::numeric, 1) AS avg_rating
        FROM reviews
        WHERE bike_id = %s
    """)
    
    with DBManager() as db:
        result = db.fetch_one(query, (bike_id,))
        return result['avg_rating']

def get_user_reviews(user_id: int) -> list:
    """Все отзывы пользователя"""
    query = sql.SQL("""
        SELECT r.*, b.type_id 
        FROM reviews r
        JOIN bikes b ON r.bike_id = b.bike_id
        WHERE user_id = %s
        ORDER BY review_date DESC
    """)
    
    with DBManager() as db:
        return db.fetch_all(query, (user_id,))

def delete_review(review_id: int) -> bool:
    """Удаление отзыва"""
    query = sql.SQL("""
        DELETE FROM reviews
        WHERE review_id = %s
    """)
    
    with DBManager() as db:
        db.execute(query, (review_id,), commit=True)
        return True
        
def get_all_rentals():
    """Получение всех аренд"""
    query = sql.SQL("SELECT * FROM rentals")
    with DBManager() as db:
        return db.fetch_all(query)

def get_completed_payments(days: int = 30):
    """Завершенные платежи за N дней"""
    query = sql.SQL("""
        SELECT * 
        FROM payments 
        WHERE 
            status = 'completed' AND 
            payment_date >= NOW() - INTERVAL '%s DAYS'
    """)
    with DBManager() as db:
        return db.fetch_all(query, (days,))

def get_station_stats():
    """Статистика по станциям"""
    query = sql.SQL("""
        SELECT 
            s.station_id,
            s.name,
            COUNT(r.rental_id) AS total_rentals
        FROM stations s
        LEFT JOIN rentals r ON s.station_id = r.start_station_id
        GROUP BY s.station_id
    """)
    with DBManager() as db:
        return db.fetch_all(query)
    
def get_bike_info(bike_id: int) -> dict:
    """Возвращает информацию о велосипеде"""
    query = sql.SQL("""
        SELECT 
            b.bike_id, 
            bt.name as type, 
            s.station_id,
            s.name as station,
            b.status
        FROM bikes b
        JOIN bike_types bt ON b.type_id = bt.type_id
        JOIN stations s ON b.station_id = s.station_id
        WHERE b.bike_id = %s
    """)
    with DBManager() as db:
        return db.fetch_one(query, (bike_id,))

def cancel_rental(rental_id: int):
    """Отмена аренды"""
    query = sql.SQL("""
        DELETE FROM rentals 
        WHERE rental_id = %s
    """)
    with DBManager() as db:
        db.execute(query, (rental_id,), commit=True)
        
def station_exists(station_id: int) -> bool:
    """Проверяет существование станции"""
    query = sql.SQL("SELECT 1 FROM stations WHERE station_id = %s")
    with DBManager() as db:
        result = db.fetch_one(query, (station_id,))
        return bool(result)
    
def create_user_if_not_exists(user_data: dict):
    """Создает пользователя, если его нет в базе"""
    query = sql.SQL("""
        INSERT INTO users (user_id, full_name, username, registration_date)
        VALUES (%(id)s, %(name)s, %(username)s, NOW())
        ON CONFLICT (user_id) DO NOTHING
    """)
    
    with DBManager() as db:
        db.execute(query, {
            "id": user_data["id"],
            "name": user_data["full_name"],
            "username": user_data["username"]
        }, commit=True)
        
def user_exists(user_id: int) -> bool:
    """Проверяет существование пользователя"""
    query = sql.SQL("SELECT 1 FROM users WHERE user_id = %s")
    with DBManager() as db:
        result = db.fetch_one(query, (user_id,))
        return bool(result)

def start_rental(user_id: int, bike_id: int, station_id: int) -> int:
    """Начинает аренду и возвращает rental_id"""
    query = sql.SQL("""
        INSERT INTO rentals (user_id, bike_id, start_station_id)
        VALUES (%s, %s, %s)
        RETURNING rental_id
    """)
    
    with DBManager() as db:
        result = db.execute(query, (user_id, bike_id, station_id), commit=True)
        return result.fetchone()['rental_id']

def check_user_role(user_id: int, role: str) -> bool:
    """Проверяет роль пользователя"""
    query = sql.SQL("SELECT 1 FROM users WHERE user_id = %s AND role = %s")
    with DBManager() as db:
        result = db.fetch_one(query, (user_id, role))
        return bool(result)
    
def get_bike_types() -> list:
    """Получение списка типов велосипедов"""
    query = "SELECT type_id, name FROM bike_types"
    with DBManager() as db:
        return db.fetch_all(query)

def get_bike_type_id(type_name: str) -> int:
    """Получение ID типа по названию"""
    query = "SELECT type_id FROM bike_types WHERE name = %s"
    with DBManager() as db:
        result = db.fetch_one(query, (type_name,))
        return result['type_id'] if result else None

def get_all_stations() -> list:
    """Получение списка всех станций"""
    query = "SELECT station_id, name FROM stations"
    with DBManager() as db:
        return db.fetch_all(query)

def get_station_id(station_name: str) -> int:
    """Получение ID станции по названию"""
    query = "SELECT station_id FROM stations WHERE name = %s"
    with DBManager() as db:
        result = db.fetch_one(query, (station_name,))
        return result['station_id'] if result else None

def add_bike(type_id: int, station_id: int) -> bool:
    """Добавление нового велосипеда"""
    query = """
        INSERT INTO bikes (type_id, station_id, status, purchase_date)
        VALUES (%s, %s, 'available', NOW())
    """
    with DBManager() as db:
        try:
            db.execute(query, (type_id, station_id), commit=True)
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления велосипеда: {e}")
            return False