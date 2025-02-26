import logging
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib
import pandas as pd
import os
from datetime import datetime, timedelta
from config import PLOT_CONFIG, LOGGING_CONFIG
from .db import get_user_rentals, get_payments_by_user, get_reviews_by_bike, get_all_rentals, get_completed_payments, get_station_stats

# Настройка логгера
logging.basicConfig(
    filename=LOGGING_CONFIG["file"],
    format=LOGGING_CONFIG["format"],
    level=LOGGING_CONFIG["level"]
)
logger = logging.getLogger(__name__)

plt.style.use(PLOT_CONFIG["default_style"])
matplotlib.rcParams['font.family'] = 'DejaVu Sans'

def _save_plot(fig, plot_name: str) -> str:
    """Сохранение графика в файл"""
    save_path = PLOT_CONFIG["save_path"]
    
    # Создание папки, если не существует
    if not os.path.exists(save_path):
        os.makedirs(save_path, exist_ok=True)
        logger.info(f"Created directory: {save_path}")

    plot_path = os.path.join(save_path, f"{plot_name}.png")
    
    try:
        fig.savefig(plot_path, dpi=PLOT_CONFIG["dpi"], bbox_inches='tight')
        logger.info(f"Plot saved: {plot_path}")
        return plot_path
    except Exception as e:
        logger.error(f"Failed to save plot: {e}")
        return None
    finally:
        plt.close(fig)

def generate_rentals_plot(user_id: int = None, days: int = 7) -> str:
    """
    Генерирует график аренд за последние N дней
    :param user_id: ID пользователя (None - все аренды)
    :param days: период в днях
    :return: путь к файлу
    """
    try:
        logger.info(f"Generating rentals plot (user_id={user_id}, days={days})")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        date_range = pd.date_range(start_date, end_date)

        # Получение данных
        raw_data = get_user_rentals(user_id) if user_id else get_all_rentals()
        df = pd.DataFrame(raw_data)
        if df.empty:
            return None

        # Фильтрация и агрегация
        df['date'] = pd.to_datetime(df['start_time']).dt.date
        filtered = df[df['date'].between(start_date.date(), end_date.date())]
        daily_counts = filtered.groupby('date').size().reindex(date_range.date, fill_value=0)

        # Построение
        fig, ax = plt.subplots(figsize=(10, 6))
        daily_counts.plot(kind='bar', ax=ax, color='#2ecc71')
        
        ax.set_title(f"Аренды за последние {days} дней")
        ax.set_xlabel("Дата")
        ax.set_ylabel("Количество аренд")
        ax.grid(axis='y', linestyle='--')

        return _save_plot(fig, f"rentals_{user_id or 'all'}")

    except Exception as e:
        logger.error(f"Rentals plot error: {e}", exc_info=True)
        return None

def generate_income_plot(days: int = 30) -> str:
    """
    Генерирует график доходов
    :param days: период в днях
    :return: путь к файлу
    """
    try:
        # Получение данных
        payments = get_completed_payments(days)
        df = pd.DataFrame(payments)
        if df.empty:
            return None

        # Преобразование данных
        df['payment_date'] = pd.to_datetime(df['payment_date'])
        df.set_index('payment_date', inplace=True)
        daily_income = df.resample('D')['amount'].sum().fillna(0)

        # Построение
        fig, ax = plt.subplots(figsize=(10, 6))
        daily_income.plot(kind='line', ax=ax, marker='o', color='#e74c3c')
        
        ax.set_title(f"Доходы за последние {days} дней")
        ax.set_xlabel("Дата")
        ax.set_ylabel("Сумма (руб.)")
        ax.grid(True, linestyle='--')

        return _save_plot(fig, "income")

    except Exception as e:
        logger.error(f"Income plot error: {e}")
        return None

def generate_rating_distribution(bike_id: int) -> str:
    """
    Распределение оценок для велосипеда
    :param bike_id: ID велосипеда
    :return: путь к файлу
    """
    try:
        reviews = get_reviews_by_bike(bike_id)
        if not reviews:
            return None

        # Агрегация данных
        ratings = [review['rating'] for review in reviews]
        rating_counts = pd.Series(ratings).value_counts().sort_index()

        # Построение
        fig, ax = plt.subplots(figsize=(8, 8))
        rating_counts.plot(
            kind='pie',
            ax=ax,
            autopct='%1.1f%%',
            colors=['#ff7675', '#74b9ff', '#55efc4', '#ffeaa7', '#a29bfe']
        )
        
        ax.set_title(f"Распределение оценок (велосипед {bike_id})")
        ax.set_ylabel("")

        return _save_plot(fig, f"ratings_{bike_id}")

    except Exception as e:
        logger.error(f"Ratings plot error: {e}")
        return None

def generate_station_activity_plot() -> str:
    """
    Активность станций (топ-5)
    :return: путь к файлу
    """
    try:
        # Получение данных
        stations = get_station_stats()
        df = pd.DataFrame(stations).nlargest(5, 'total_rentals')

        # Построение
        fig, ax = plt.subplots(figsize=(10, 6))
        df.plot(
            kind='barh',
            x='name',
            y='total_rentals',
            ax=ax,
            color='#3498db'
        )
        
        ax.set_title("Топ-5 станций по арендам")
        ax.set_xlabel("Количество аренд")
        ax.set_ylabel("Станция")
        ax.invert_yaxis()

        return _save_plot(fig, "station_activity")

    except Exception as e:
        logger.error(f"Station activity plot error: {e}")
        return None