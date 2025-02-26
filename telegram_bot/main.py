import io
from logging.handlers import RotatingFileHandler
import os
import logging
import tempfile
import pandas as pd
from datetime import datetime, timedelta

from telegram import (
    ReplyKeyboardRemove,
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InputFile
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from config import (
    TELEGRAM_CONFIG,
    LOGGING_CONFIG,
    PLOT_CONFIG
)
from utils.db import (
    get_available_bikes,
    get_user_rentals,
    start_rental,
    close_rental,
    get_payments_by_user,
    add_review,
    get_average_rating,
    check_user_role,
    get_bike_info,
    cancel_rental,
    create_user_if_not_exists,
    user_exists,
    station_exists,
    add_bike,
    get_station_id,
    get_all_stations,
    get_bike_type_id,
    get_bike_types
)
from utils.plots import (
    generate_rentals_plot,
    generate_income_plot,
    generate_rating_distribution
)

# Настройка логирования
logging.basicConfig(
    format=LOGGING_CONFIG["format"],
    level=LOGGING_CONFIG["level"]
)

file_handler = RotatingFileHandler(
    'app.log', 
    encoding='utf-8', 
    maxBytes=5*1024*1024,  # 5 MB
    backupCount=3
)

logger = logging.getLogger(__name__)
logger.addHandler(file_handler)

# Состояния для ConversationHandler

(
    SELECT_BIKE,
    CONFIRM_RENTAL,
    RENTAL_IN_PROGRESS,
    END_STATION_INPUT,
    REVIEW_RATING,
    REVIEW_COMMENT
) = range(6)

(ADD_BIKE_TYPE, ADD_BIKE_STATION, ADD_BIKE_CONFIRM) = range(3)

class BikeRentalBot:
    def __init__(self):
        self.application = ApplicationBuilder().token(TELEGRAM_CONFIG["token"]).build()
        self.user_states = {}
        self.user_rentals = {}  #############
        self._register_handlers()

    def _register_handlers(self):
        """Регистрация обработчиков с обновленными зависимостями"""
        
        self.application.add_handler(self._rental_conversation_handler()) ####################################
        self.application.add_handler(self._ratings_conversation_handler())
        
        self.application.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^➕ Добавить велосипед$"), self.start_add_bike)],
        states={
            ADD_BIKE_TYPE: [MessageHandler(filters.TEXT, self.process_bike_type)],
            ADD_BIKE_STATION: [MessageHandler(filters.TEXT, self.process_bike_station)],
            ADD_BIKE_CONFIRM: [MessageHandler(filters.Regex(r"^(✅ Подтвердить|❌ Отменить)$"), self.confirm_add_bike)]
        },
        fallbacks=[CommandHandler("cancel", lambda u,c: self.cancel_conversation(u,c, "Добавление велосипеда отменено"))]
        ))
            
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help))
        
        # self.application.add_handler(MessageHandler(filters.TEXT, self.handle_message))
        
        # self.application.add_handler(MessageHandler(
        #     filters.TEXT & ~filters.COMMAND, 
        #     self.handle_bike_id_input
        # ))
        

        
        
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.handle_message
        ))        
        
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_bike_id_input
        ))

        # self.application.add_handler(ConversationHandler(
        #     entry_points=[CommandHandler("review", self.start_review)],
        #     states={
        #         RATING: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_rating)],
        #         COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_comment)]
        #     },
        #     fallbacks=[CommandHandler("cancel", self.cancel_review)],
        #     map_to_parent={
        #         ConversationHandler.END: None
        #     }
        # ))
        
        
        # self.application.add_handler(ConversationHandler(
        #     entry_points=[MessageHandler(filters.Regex("🚲 Арендовать велосипед"), self.start_rental)],
        #     states={
        #         SELECT_BIKE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.select_bike)],
        #         CONFIRM_RENTAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.confirm_rental)],
        #         RENTAL_IN_PROGRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.rental_actions)],
        #         REVIEW_RATING: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_review_rating)],
        #         REVIEW_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_review_comment)]
        #     },
        #     fallbacks=[CommandHandler("cancel", self.cancel_rental)]
        # ))
        self.application.add_error_handler(self.error_handler)
        

    def _main_menu(self, user_id: int = None):
        """Главное меню с reply-кнопками"""
        buttons = [
            [KeyboardButton("🚲 Арендовать велосипед")],
            [KeyboardButton("📖 Мои аренды"), KeyboardButton("📊 Статистика")],
            [KeyboardButton("❓ Помощь")]
        ]
        
        # Добавляем кнопку администратора
        if user_id and self._is_admin(user_id):
            buttons.insert(1, [KeyboardButton("➕ Добавить велосипед")])
        
        return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

    def _is_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь администратором"""
        return check_user_role(user_id, "admin")

    def _rental_menu(self):
        """Меню во время аренды"""
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton("🔙 Завершить аренду")],
                [KeyboardButton("❌ Отменить аренду")]
            ],
            resize_keyboard=True
        )
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        
        user_data = {
            "id": user.id,
            "full_name": user.full_name,
            "username": user.username
        }
        
        create_user_if_not_exists(user_data)
        
        await update.message.reply_text(
            f"Привет, {user.first_name}!",
            reply_markup=self._main_menu(user.id)
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = (
            "📚 Доступные команды:\n"
            "🚲 Доступные велосипеды - показать свободные\n"
            "📖 Мои аренды - история аренд\n"
            "📊 Статистика - аналитика системы\n"
            "❓ Помощь - эта справка"
        )
        await update.message.reply_text(help_text)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений"""
        
        if context.user_data.get('in_conversation'):
            return
        
        text = update.message.text
        handlers = {
            "🚲 Арендовать велосипед": self.start_rental,
            "📖 Мои аренды": self.show_user_rentals,
            "📊 Статистика": self.show_stats_menu,
            "➕ Добавить велосипед": self.start_add_bike,
            "🔙 Назад": self.start,
            "❓ Помощь": self.help,            
            
            "📈 Аренды": self.show_rentals_stats,
            "💰 Доходы": self.show_income_stats,
            "⭐ Рейтинги": self.show_ratings_stats,                        
            
            "🔙 Назад": self.start,
            "❌ Отменить аренду": self.cancel_rental
        }
        
        if text in handlers:
            await handlers[text](update, context)
        else:
            await update.message.reply_text(
                "⚠️ Неизвестная команда",
                reply_markup=self._main_menu()
            )

    async def show_stats_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню статистики"""
        reply_markup = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton("📈 Аренды"), KeyboardButton("💰 Доходы")],
                [KeyboardButton("⭐ Рейтинги"), KeyboardButton("🔙 Назад")]
            ],
            resize_keyboard=True
        )
        await update.message.reply_text(
            "Выберите тип статистики:",
            reply_markup=reply_markup
        )

    async def show_available_bikes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать доступные велосипеды"""
        try:
            bikes = get_available_bikes()
            if not bikes:
                await update.message.reply_text("😞 Нет доступных велосипедов")
                return

            response = ["🚴 Доступные велосипеды:\n"]
            for bike in bikes:
                response.append(
                    f"ID: {bike['bike_id']}\n"
                    f"Тип: {bike['type']}\n"
                    f"Станция: {bike['station']}\n"
                    f"Цена: {bike['price_per_hour']} руб/час\n"
                )

            await update.message.reply_text("\n".join(response))
        except Exception as e:
            logger.error(f"Available bikes error: {e}")
            await update.message.reply_text("⚠️ Ошибка при получении данных")

    async def start_add_bike(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало процесса добавления велосипеда"""
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Доступ запрещен")
            return ConversationHandler.END
        
        # Получаем список типов велосипедов
        bike_types = get_bike_types()  
        if not bike_types:
            await update.message.reply_text("❌ Нет доступных типов велосипедов")
            return ConversationHandler.END
        
        # Формируем клавиатуру с типами
        keyboard = [[t['name']] for t in bike_types]
        keyboard.append(["🔙 Отмена"])
        
        await update.message.reply_text(
            "🚴 Выберите тип велосипеда:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return ADD_BIKE_TYPE

    async def process_bike_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбранного типа"""
        selected_type = update.message.text
        type_id = get_bike_type_id(selected_type)  
        
        if not type_id:
            await update.message.reply_text("❌ Неверный тип велосипеда")
            return ADD_BIKE_TYPE
        
        context.user_data['new_bike'] = {'type_id': type_id}
        
        # Получаем список станций
        stations = get_all_stations()  
        keyboard = [[s['name']] for s in stations]
        keyboard.append(["🔙 Отмена"])
        
        await update.message.reply_text(
            "📍 Выберите станцию:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return ADD_BIKE_STATION

    async def process_bike_station(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбранной станции"""
        station_name = update.message.text
        station_id = get_station_id(station_name)  
        
        if not station_id:
            await update.message.reply_text("❌ Станция не найдена")
            return ADD_BIKE_STATION
        
        context.user_data['new_bike']['station_id'] = station_id
        
        # Подтверждение
        await update.message.reply_text(
            f"Создать велосипед?\n"
            f"Тип: {update.message.text}\n"
            f"Станция: {station_name}",
            reply_markup=ReplyKeyboardMarkup([["✅ Подтвердить", "❌ Отменить"]], resize_keyboard=True)
        )
        return ADD_BIKE_CONFIRM

    async def confirm_add_bike(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Финальное подтверждение"""
        if update.message.text == "✅ Подтвердить":
            bike_data = context.user_data['new_bike']
            if add_bike(**bike_data):  
                await update.message.reply_text("✅ Велосипед успешно добавлен", reply_markup=self._main_menu())
            else:
                await update.message.reply_text("⚠️ Ошибка при добавлении", reply_markup=self._main_menu())
        else:
            await update.message.reply_text("❌ Добавление отменено", reply_markup=self._main_menu())
        
        context.user_data.clear()
        return ConversationHandler.END

    async def start_rental(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало процесса аренды"""
        try:
            bikes = get_available_bikes()
            if not bikes:
                await update.message.reply_text("😞 Нет доступных велосипедов")
                return ConversationHandler.END
                
            bike_list = "\n".join(
                f"{b['bike_id']} - {b['type']} ({b['station']}), цена: {b['price_per_hour']} ₽/час" 
                for b in bikes
            )
            
            await update.message.reply_text(
                f"🚲 Доступные велосипеды:\n{bike_list}\n"
                "Введите ID велосипеда для аренды:",
                reply_markup=ReplyKeyboardRemove()
            )
            return SELECT_BIKE
            
        except Exception as e:
            logger.error(f"Start rental error: {e}")
            await update.message.reply_text("⚠️ Ошибка при получении данных")
            return ConversationHandler.END

    async def select_bike(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выбор велосипеда"""
        try:
            bike_id = int(update.message.text)
            bike = get_bike_info(bike_id) 
            
            if not bike or bike['status'] != 'available':
                await update.message.reply_text("❌ Этот велосипед недоступен")
                return ConversationHandler.END
                
            context.user_data['rental'] = {
                'bike_id': bike_id,
                'start_station': bike['station_id']
            }
            
            reply_markup = ReplyKeyboardMarkup(
                [[KeyboardButton("✅ Подтвердить"), KeyboardButton("❌ Отменить")]],
                resize_keyboard=True
            )
            
            await update.message.reply_text(
                f"Вы выбрали велосипед {bike_id}\n"
                f"Тип: {bike['type']}\n"
                f"Станция: {bike['station']}\n\n"
                "Подтвердите аренду:",
                reply_markup=reply_markup
            )
            return CONFIRM_RENTAL
            
        except KeyError as e:
            logger.error(f"Key error in select_bike: {str(e)}")
            await update.message.reply_text("⚠️ Внутренняя ошибка данных")
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("❌ Введите числовой ID")
            return SELECT_BIKE

        
    async def confirm_rental(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Подтверждение аренды"""
        if update.message.text == "✅ Подтвердить":
            try:
                user_id = update.effective_user.id
                rental_data = context.user_data['rental']
                
                if not user_exists(user_id):
                    create_user_if_not_exists({
                        "id": user_id,
                        "full_name": update.effective_user.full_name,
                        "username": update.effective_user.username
                    })
                
                rental_id = start_rental(
                    user_id=user_id,
                    bike_id=rental_data['bike_id'],
                    station_id=rental_data['start_station']
                )
                
                self.user_rentals[update.message.chat_id] = rental_id
                await update.message.reply_text("🚴 Аренда начата!", reply_markup=self._rental_menu())
                return RENTAL_IN_PROGRESS
                
            except Exception as e:
                logger.error(f"Confirm rental error: {e}", exc_info=True)
                await update.message.reply_text("⚠️ Ошибка при старте аренды")
                return ConversationHandler.END
        else:
            await update.message.reply_text("❌ Аренда отменена")
            return ConversationHandler.END

    def _rental_conversation_handler(self):
        return ConversationHandler(
            entry_points=[MessageHandler(filters.Regex("^🚲 Арендовать велосипед$"), self.start_rental)],
            states={
                SELECT_BIKE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.select_bike)
                ],
                CONFIRM_RENTAL: [
                    MessageHandler(filters.Regex("^(✅ Подтвердить|❌ Отменить)$"), self.confirm_rental)
                ],
                RENTAL_IN_PROGRESS: [
                    MessageHandler(filters.Regex("^(🔙 Завершить аренду|❌ Отменить аренду)$"), self.rental_actions)
                ],
                END_STATION_INPUT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_end_station)
                ],
                REVIEW_RATING: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_review_rating)
                ],
                REVIEW_COMMENT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_review_comment)
                ]
            },
            fallbacks=[CommandHandler("cancel", self.cancel_rental)],
            map_to_parent={ConversationHandler.END: None}
        )

    def _ratings_conversation_handler(self):
        return ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex("^⭐ Рейтинги$"), self.show_ratings_stats)
            ],
            states={
                REVIEW_RATING: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_bike_id_input)
                ]
            },
            fallbacks=[
                CommandHandler("cancel", self.cancel_ratings)
            ],
            map_to_parent={ConversationHandler.END: None}
        )
    async def rental_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Действия во время аренды"""
        if update.message.text == "🔙 Завершить аренду":
            await update.message.reply_text(
                "Введите ID станции возврата:",
                reply_markup=ReplyKeyboardRemove()
            )
            return END_STATION_INPUT
        else:
            await update.message.reply_text(
                "🚴 Аренда активна. Используйте меню ниже:",
                reply_markup=self._rental_menu()
            )
            return RENTAL_IN_PROGRESS
        
    async def process_end_station(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ID станции возврата"""
        try:
            end_station_id = int(update.message.text)
            
            # Проверка существования станции
            if not station_exists(end_station_id):
                await update.message.reply_text("❌ Станция не найдена")
                return END_STATION_INPUT
            
            # Сохраняем station_id в контекст
            context.user_data['end_station'] = end_station_id
            
            # Запрашиваем оценку
            await update.message.reply_text(
                "⭐ Оцените аренду (1-5):",
                reply_markup=ReplyKeyboardMarkup([[str(i) for i in range(1, 6)]], resize_keyboard=True)
            )
            return REVIEW_RATING
            
        except ValueError:
            await update.message.reply_text("❌ Введите числовой ID станции")
            return END_STATION_INPUT

    async def show_user_rentals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать аренды пользователя"""
        try:
            user_id = update.effective_user.id
            rentals = get_user_rentals(user_id)
            
            if not rentals:
                await update.message.reply_text("📭 У вас нет активных аренд")
                return
            
            df = pd.DataFrame(rentals)
            
            datetime_columns = ['start_time', 'end_time']
            for col in datetime_columns:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col]).dt.strftime('%Y-%m-%d %H:%M')
            
           
            columns_order = [
                'rental_id', 
                'start_time', 
                'end_time', 
                'start_station', 
                'end_station', 
                'bike_id', 
                'bike_type'
            ]
            df = df[columns_order]

            # Создаем CSV в памяти
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            csv_buffer.seek(0)

            # Отправляем файл
            await update.message.reply_document(
                document=InputFile(
                    io.BytesIO(csv_buffer.getvalue().encode()),
                    filename="my_rentals.csv"
                ),
                caption="📊 История ваших аренд"
            )

        except Exception as e:
            logger.error(f"User rentals CSV error: {e}")
            await update.message.reply_text("⚠️ Ошибка при формировании отчета")

    async def show_rentals_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """График аренд за последнюю неделю"""
        try:
            plot_path = generate_rentals_plot()
            if plot_path and os.path.exists(plot_path):
                await update.message.reply_photo(
                    photo=open(plot_path, 'rb'),
                    caption="📈 Аренды за последние 7 дней"
                )
            else:
                await update.message.reply_text("📭 Нет данных об арендах за этот период")
        except Exception as e:
            logger.error(f"Rentals stats error: {e}")
            await update.message.reply_text("⚠️ Ошибка при генерации графика")

    async def show_income_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """График доходов за последний месяц"""
        try:
            plot_path = generate_income_plot()
            if plot_path and os.path.exists(plot_path):
                await update.message.reply_photo(
                    photo=open(plot_path, 'rb'),
                    caption="💰 Доходы за последние 30 дней"
                )
            else:
                await update.message.reply_text("📭 Нет данных о доходах за этот период")
        except Exception as e:
            logger.error(f"Income stats error: {e}")
            await update.message.reply_text("⚠️ Ошибка при генерации графика")

    async def show_ratings_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало процесса запроса рейтингов"""
        try:
            await update.message.reply_text(
                "🚴 Введите ID велосипеда:",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🔙 Отмена")]], resize_keyboard=True)
            )
            return REVIEW_RATING
        except Exception as e:
            logger.error(f"Ratings start error: {e}")
            return ConversationHandler.END
        
        
    async def handle_bike_id_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка введенного ID"""
        try:
            bike_id = int(update.message.text)
            plot_path = generate_rating_distribution(bike_id)
            
            if plot_path:
                await update.message.reply_photo(
                    photo=open(plot_path, 'rb'),
                    caption=f"⭐ Рейтинги велосипеда {bike_id}",
                    reply_markup=self._main_menu()
                )
            else:
                await update.message.reply_text(
                    "🚴 Нет данных для этого велосипеда",
                    reply_markup=self._main_menu()
                )
            return ConversationHandler.END

        except ValueError:
            await update.message.reply_text("❌ Введите число!")
            return REVIEW_RATING
        except Exception as e:
            logger.error(f"Ratings error: {e}")
            return ConversationHandler.END


    async def cancel_ratings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена запроса рейтингов"""
        await update.message.reply_text("❌ Запрос отменен", reply_markup=self._main_menu())
        return ConversationHandler.END
    # async def start_review(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    #     """Начало процесса добавления отзыва"""
    #     try:
    #         await update.message.reply_text(
    #             "🚴 Оставьте отзыв о велосипеде\n"
    #             "Введите ID велосипеда:",
    #             reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🔙 Назад")]], resize_keyboard=True)
    #         )
    #         return RATING
    #     except Exception as e:
    #         logger.error(f"Start review error: {e}")
    #         return ConversationHandler.END

    # async def get_rating(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    #     """Обработка оценки"""
    #     try:
    #         bike_id = int(update.message.text)
    #         context.user_data["bike_id"] = bike_id
    #         await update.message.reply_text(
    #             "⭐ Оцените велосипед от 1 до 5:",
    #             reply_markup=ReplyKeyboardMarkup(
    #                 [[str(i) for i in range(1, 6)] + [KeyboardButton("🔙 Назад")]],
    #                 resize_keyboard=True
    #             )
    #         )
    #         return COMMENT
    #     except ValueError:
    #         await update.message.reply_text("❌ Неверный формат ID. Попробуйте снова.")
    #         return RATING

    # async def get_comment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    #     """Обработка комментария"""
    #     try:
    #         rating = int(update.message.text)
    #         if 1 <= rating <= 5:
    #             bike_id = context.user_data["bike_id"]
    #             user_id = update.effective_user.id
                
    #             add_review(user_id, bike_id, rating)
    #             avg_rating = get_average_rating(bike_id)
                
    #             await update.message.reply_text(
    #                 f"✅ Спасибо за отзыв!\nСредний рейтинг велосипеда: {avg_rating}/5",
    #                 reply_markup=self._main_menu()
    #             )
    #             return ConversationHandler.END
    #         else:
    #             await update.message.reply_text("❌ Оценка должна быть от 1 до 5")
    #             return COMMENT
    #     except ValueError:
    #         await update.message.reply_text("❌ Неверный формат оценки")
    #         return COMMENT

    async def process_review_rating(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка оценки аренды"""
        try:
            rating = int(update.message.text)
            if not (1 <= rating <= 5):
                raise ValueError
            
            # Сохраняем оценку в контексте
            context.user_data['rating'] = rating
            
            await update.message.reply_text(
                "💬 Напишите комментарий (или нажмите 'Пропустить'):",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🚫 Пропустить")]], resize_keyboard=True)
            )
            return REVIEW_COMMENT
            
        except ValueError:
            await update.message.reply_text("❌ Оценка должна быть от 1 до 5")
            return REVIEW_RATING

    # async def process_review_comment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    #     """Обработка комментария к отзыву"""
    #     try:
    #         rating = None
    #         if update.message.text.isdigit():
    #             rating = int(update.message.text)
    #             if not (1 <= rating <= 5):
    #                 raise ValueError
            
    #         # Завершаем аренду
    #         rental_id = self.user_rentals.get(update.message.chat_id)
    #         close_rental(
    #             rental_id=rental_id,
    #             end_station_id=context.user_data['end_station']
    #         )
            
    #         # Сохраняем отзыв
    #         if rating:
    #             add_review(
    #                 user_id=update.effective_user.id,
    #                 bike_id=context.user_data['rental']['bike_id'],
    #                 rating=rating
    #             )
            
    #         await update.message.reply_text(
    #             "✅ Аренда завершена! Спасибо за использование нашего сервиса.",
    #             reply_markup=self._main_menu()
    #         )
    #         return ConversationHandler.END
            
    #     except ValueError:
    #         await update.message.reply_text("❌ Неверный формат оценки")
    #         return REVIEW_COMMENT
    
    
    async def process_review_comment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            # Получаем данные из контекста
            end_station_id = context.user_data.get('end_station')
            rental_id = self.user_rentals.get(update.message.chat_id)
            rating = context.user_data.get('rating')
            
            if not end_station_id or not rental_id:
                raise ValueError("Недостаточно данных для завершения аренды")
            
            # Завершаем аренду
            if not close_rental(rental_id, end_station_id):
                raise RuntimeError("Ошибка при закрытии аренды")
            
            # Сохраняем отзыв, если есть оценка
            if rating:
                add_review(
                    user_id=update.effective_user.id,
                    bike_id=context.user_data['rental']['bike_id'],
                    rating=rating,
                    comment=update.message.text if update.message.text != "🚫 Пропустить" else None
                )
                await update.message.reply_text("⭐ Спасибо за отзыв!", reply_markup=self._main_menu())
            else:
                await update.message.reply_text("✅ Аренда завершена", reply_markup=self._main_menu())
            
            # Очистка данных
            del self.user_rentals[update.message.chat_id]
            context.user_data.clear()
            
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"Ошибка завершения: {str(e)}")
            await update.message.reply_text("⚠️ Критическая ошибка")
            return ConversationHandler.END

    async def cancel_rental(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена аренды"""
        if update.message.chat_id in self.user_rentals:
            cancel_rental(self.user_rentals[update.message.chat_id])  # Новая функция в utils.db
            del self.user_rentals[update.message.chat_id]
            
        await update.message.reply_text(
            "❌ Аренда отменена",
            reply_markup=self._main_menu()
        )
        return ConversationHandler.END

    async def cancel_review(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена оставления отзыва"""
        await update.message.reply_text(
            "❌ Отмена оставления отзыва",
            reply_markup=self._main_menu()
        )
        return ConversationHandler.END
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Глобальный обработчик ошибок"""
        logger.error(msg="Exception while handling update:", exc_info=context.error)
        
        error_text = (
            "⚠️ Произошла непредвиденная ошибка.\n"
            "Администратор уже уведомлен и работает над решением проблемы."
        )
        
        if update.message:
            await update.message.reply_text(error_text)
        
        for admin_id in TELEGRAM_CONFIG["admin_ids"]:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🚨 Ошибка в боте:\n{context.error}"
            )

    def run(self):
        """Запуск бота"""
        self.application.run_polling()

if __name__ == "__main__":
    bot = BikeRentalBot()
    bot.run()