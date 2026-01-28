import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime
from difflib import get_close_matches
import re

st.set_page_config(page_title="WB Unit Economics", layout="centered")
st.title("Калькулятор расчета себестоимости WB")

# =========================
# ФАЙЛ КОМИССИЙ
# =========================

DATA_DIR = Path("data")
COMMISSION_FILE = DATA_DIR / "Комиссии ВБ.xlsx"

if not COMMISSION_FILE.exists():
    st.error("Файл комиссий не найден. Проверь папку data/")
    st.stop()

df_commission = pd.read_excel(COMMISSION_FILE)
updated_at = datetime.fromtimestamp(COMMISSION_FILE.stat().st_mtime)

st.success("Файл комиссий подключён")
st.caption(f"Дата обновления: {updated_at.strftime('%d.%m.%Y %H:%M')}")

st.divider()

# =========================
# ВВОД КАТЕГОРИИ
# =========================

category_input = st.text_input(
    "Введите категорию WB (предмет)",
    placeholder="например: Джинсы"
)

result_row = None

if category_input:
    subjects = (
        df_commission["Предмет"]
        .dropna()
        .astype(str)
        .tolist()
    )

    matches = get_close_matches(
        category_input,
        subjects,
        n=1,
        cutoff=0.4
    )

    if matches:
        found_category = matches[0]
        result_row = df_commission[df_commission["Предмет"] == found_category].iloc[0]
    else:
        st.warning("Категория не найдена")

# =========================
# ВЫВОД КАТЕГОРИИ И КОМИССИЙ
# =========================

if result_row is not None:
    st.divider()
    st.subheader("Найденная категория")

    st.write(f"**Категория:** {result_row['Предмет']}")

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            label="Комиссия FBW",
            value=f"{result_row['Склад WB, %']} %"
        )

    with col2:
        st.metric(
            label="Комиссия FBS",
            value=f"{result_row['Склад продавца - везу на склад WB, %']} %"
        )

# =========================
# ВЫКУП ИЗ ВОРОНКИ ПРОДАЖ (ВЗВЕШЕННЫЙ ПО ЗАКАЗАМ)
# =========================

if result_row is not None:
    FUNNEL_FILE = Path("data/Воронка продаж.xlsx")

    if FUNNEL_FILE.exists():
        funnel_df = pd.read_excel(
            FUNNEL_FILE,
            sheet_name="Товары"
        )

        # нормализация названий колонок
        funnel_df.columns = (
            funnel_df.columns
            .astype(str)
            .str.replace("\xa0", " ", regex=False)
            .str.strip()
        )

        funnel_filtered = funnel_df[
            funnel_df["Предмет"] == result_row["Предмет"]
        ]

        if not funnel_filtered.empty:

            # чистим % выкупа (на случай формата '56%')
            buyout = (
                funnel_filtered["Процент выкупа"]
                .astype(str)
                .str.replace("%", "", regex=False)
                .astype(float)
            )

            # ВЕС — ЗАКАЗЫ (ЭТО ПРИНЦИПИАЛЬНО)
            orders = funnel_filtered["Заказали, шт"]

            avg_buyout = (buyout * orders).sum() / orders.sum()

            st.divider()
            st.subheader("% выкупа")

            st.metric(
                label="Средний % выкупа (взвешенный по заказам)",
                value=f"{avg_buyout:.1f} %"
            )

        else:
            st.warning("По выбранному предмету нет данных о выкупе")

    else:
        st.warning("Файл «Воронка продаж.xlsx» не найден в папке data/")


# =========================
# ЦЕНОВЫЕ ОРИЕНТИРЫ
# =========================

st.divider()
st.subheader("Ценовые ориентиры")

col_left, col_right = st.columns(2)

# =========================
# ЛЕВЫЙ БЛОК — EVIRMA
# =========================

with col_left:
    st.markdown("### Цена по рынку (Evirma)")

    price_text = st.text_area(
        "Вставьте распределение цен (из Evirma)",
        height=200,
        placeholder="46%\n383 ₽ — 1 696 ₽"
    )

    auto_price_evirma = None

    if price_text.strip():
        blocks = re.findall(
            r"(\d+)%\s*\n([\d\s]+) ₽ — ([\d\s]+) ₽",
            price_text
        )

        if blocks:
            max_block = max(blocks, key=lambda x: int(x[0]))

            percent = int(max_block[0])
            min_price = int(max_block[1].replace(" ", ""))
            max_price = int(max_block[2].replace(" ", ""))

            avg_price = (min_price + max_price) / 2
            auto_price_evirma = round(avg_price * 1.15)

            st.success(
                f"Основной диапазон: {min_price:,} – {max_price:,} ₽ ({percent}%)"
                .replace(",", " ")
            )
            st.info(
                f"Расчётная цена (midpoint +15%): {auto_price_evirma:,} ₽"
                .replace(",", " ")
            )
        else:
            st.error("Не удалось распознать формат. Проверь вставленный текст.")

# =========================
# ПРАВЫЙ БЛОК — MPSTATS
# =========================

with col_right:
    st.markdown("### Цена по спросу (MPStats)")

    mpstats_text = st.text_area(
        "Вставьте таблицу из MPStats (От / До / Продажи, шт)",
        height=260,
        placeholder=(
            "От\tДо\tПродажи, шт.\n"
            "5\t504\t18954\n"
            "505\t1004\t289568\n"
            "1005\t1504\t668883"
        )
    )

    auto_price_mpstats = None

    if mpstats_text.strip():
        try:
            mp_df = pd.read_csv(
                pd.io.common.StringIO(mpstats_text),
                sep="\t"
            )
        except Exception:
            try:
                mp_df = pd.read_csv(
                    pd.io.common.StringIO(mpstats_text),
                    sep=r"\s{2,}",
                    engine="python"
                )
            except Exception:
                st.error("Не удалось распознать таблицу MPStats")
                mp_df = None

        if mp_df is not None:
            # нормализация колонок
            mp_df.columns = (
                mp_df.columns.astype(str)
                .str.replace("\xa0", " ", regex=False)
                .str.strip()
                .str.replace(".", "", regex=False)
            )

            required_cols = ["От", "До", "Продажи, шт"]
            missing = [c for c in required_cols if c not in mp_df.columns]

            if missing:
                st.error("Не найдены колонки: " + ", ".join(missing))
            else:
                # приведение типов
                mp_df["От"] = (
                    mp_df["От"].astype(str)
                    .str.replace(" ", "")
                    .astype(float)
                )
                mp_df["До"] = (
                    mp_df["До"].astype(str)
                    .str.replace(" ", "")
                    .astype(float)
                )
                mp_df["Продажи, шт"] = (
                    mp_df["Продажи, шт"].astype(str)
                    .str.replace(" ", "")
                    .astype(float)
                )

                # 1️⃣ диапазон с максимальными продажами
                top_row = mp_df.loc[
                    mp_df["Продажи, шт"].idxmax()
                ]

                min_p = top_row["От"]
                max_p = top_row["До"]
                sales = int(top_row["Продажи, шт"])

                # 2️⃣ midpoint + 15%
                midpoint = (min_p + max_p) / 2
                auto_price_mpstats = round(midpoint * 1.15)

                st.success(
                    f"Топ-диапазон по продажам: "
                    f"{int(min_p):,} – {int(max_p):,} ₽ "
                    f"(продаж: {sales:,})"
                    .replace(",", " ")
                )

                st.info(
                    f"Расчётная цена (midpoint +15%): "
                    f"{auto_price_mpstats:,} ₽"
                    .replace(",", " ")
                )

# =========================
# ВЫБОР БАЗОВОЙ ЦЕНЫ
# =========================

auto_prices = []

if auto_price_evirma is not None:
    auto_prices.append(auto_price_evirma)

if 'auto_price_mpstats' in locals() and auto_price_mpstats is not None:
    auto_prices.append(auto_price_mpstats)

auto_price_final = max(auto_prices) if auto_prices else 0

# =========================
# ОБЩАЯ ЦЕНА ДЛЯ РАСЧЁТА
# =========================

st.divider()

base_price = st.number_input(
"Целевая цена для покупателя, ₽",
min_value=0,
value=int(auto_price_final),
step=10
)

# =========================
# СПП (СКИДКА ПОСТОЯННОГО ПОКУПАТЕЛЯ)
# =========================

st.divider()
st.subheader("СПП (скидка WB)")

# СПП — дефолт 25%
spp = st.number_input(
    "СПП, %",
    min_value=0.0,
    max_value=50.0,
    value=25.0,      # ← ВАЖНО: дефолт 25%
    step=0.5
)

# цена для клиента (с СПП)
price_client = base_price

# цена для расчёта юнит-экономики (без СПП)
if price_client > 0 and spp < 100:
    price_for_calc = round(price_client / (1 - spp / 100))
else:
    price_for_calc = 0

# вывод
col_a, col_b = st.columns(2)

with col_a:
    st.metric(
        label="Таргетная цена на рынке (для покупателя, с СПП)",
        value=f"{price_client:,} ₽".replace(",", " ")
    )

with col_b:
    st.metric(
        label="Цена для расчёта юнит-экономики (без СПП)",
        value=f"{price_for_calc:,} ₽".replace(",", " ")
    )


# =========================
# РАСЧЁТ ОБЪЁМА (ЛИТРЫ)
# =========================

st.divider()
st.subheader("Габариты и объём")

col1, col2, col3, col4 = st.columns(4)

with col1:
    length_cm = st.number_input(
        "Длина, см",
        min_value=0.0,
        value=25.0,
        step=0.5,
        format="%.1f"
    )

with col2:
    width_cm = st.number_input(
        "Ширина, см",
        min_value=0.0,
        value=30.0,
        step=0.5,
        format="%.1f"
    )

with col3:
    height_cm = st.number_input(
        "Высота, см",
        min_value=0.0,
        value=15.0,
        step=0.5,
        format="%.1f"
    )

with col4:
    weight_kg = st.number_input(
        "Вес, кг",
        min_value=0.0,
        value=2.0,
        step=0.5,
        format="%.1f"
    )

# объём в литрах
volume_l = round(length_cm * width_cm * height_cm / 1000, 2)

st.metric("Расчётный объём, л", f"{volume_l:.2f}")

# =========================
# ЦЕЛЕВЫЕ ПАРАМЕТРЫ
# =========================

st.divider()
st.subheader("Целевые параметры")

target_gm = st.number_input(
    "Целевая валовая рентабельность, %",
    min_value=0.0,
    max_value=100.0,
    value=21.0,
    step=0.5
)

ad_share = st.number_input(
    "ДРР (реклама), % от цены",
    min_value=0.0,
    max_value=100.0,
    value=7.0,
    step=0.5
)

# =========================
# ЛОГИСТИКА WB — ВЫБОР ПАРАМЕТРОВ
# =========================

st.divider()
st.subheader("Логистика WB")

TARIFF_FILE = DATA_DIR / "Тарифы на логистику.xlsx"

if not TARIFF_FILE.exists():
    st.error("Файл «Тарифы на логистику.xlsx» не найден в папке data/")
    st.stop()

# модель поставки
supply_model = st.radio(
    "Модель поставки",
    ["FBW", "FBS"],
    horizontal=True
)

# тип поставки
package_type = st.radio(
    "Тип поставки",
    ["Короба", "Монопаллеты"],
    horizontal=True
)

# читаем нужный лист
tariff_df = pd.read_excel(
    TARIFF_FILE,
    sheet_name=package_type
)

# чистим колонки
tariff_df.columns = (
    tariff_df.columns
    .astype(str)
    .str.replace("\xa0", " ", regex=False)
    .str.strip()
)

# проверка колонки склада
if "Склад" not in tariff_df.columns:
    st.error("В файле тарифов нет колонки «Склад»")
    st.stop()

# СГТ
is_sgt = st.radio(
    "Склад СГТ",
    ["Нет", "Да"],
    horizontal=True
)

# все склады
all_warehouses = tariff_df["Склад"].dropna().unique().tolist()

# 1️⃣ фильтр по модели поставки
if supply_model == "FBS":
    model_filtered = [
        w for w in all_warehouses
        if w.strip().lower().startswith("маркетплейс")
    ]
else:  # FBW
    model_filtered = [
        w for w in all_warehouses
        if not w.strip().lower().startswith("маркетплейс")
    ]

# 2️⃣ фильтр по СГТ
if is_sgt == "Да":
    filtered_warehouses = [
        w for w in model_filtered
        if w.strip().endswith("СГТ")
    ]
else:
    filtered_warehouses = [
        w for w in model_filtered
        if not w.strip().endswith("СГТ")
    ]

if not filtered_warehouses:
    st.error("Нет складов под выбранные условия (модель поставки / СГТ)")
    st.stop()

# сортировка + дефолт Электросталь
filtered_warehouses = sorted(filtered_warehouses)

default_index = (
    filtered_warehouses.index("Электросталь")
    if "Электросталь" in filtered_warehouses
    else 0
)

# выбор склада
warehouse = st.selectbox(
    "Склад WB",
    filtered_warehouses,
    index=default_index
)

# выбранная строка тарифа
tariff_selected = tariff_df[
    tariff_df["Склад"] == warehouse
]

st.success(
    f"Выбрано: {supply_model} / {package_type} / {warehouse}"
)

# =========================
# РАСЧЁТ ЛОГИСТИКИ / ХРАНЕНИЯ (ЗА 1 ШТ / ПАЛЛЕТУ)
# =========================

st.divider()
st.subheader("Логистика и хранение")

def to_float(x):
    x = str(x).strip()
    if x in ["-", "", "nan", "None"]:
        return 0.0
    return float(x.replace(" ", "").replace(",", "."))

row = tariff_selected.iloc[0]

# ---------- ЛОГИСТИКА ----------
if supply_model == "FBS":
    coef_log = to_float(row.get("Коэффициент FBS, %", 0))
    base_log = to_float(row.get("Логистика за 1 л, FBS", row["Логистика за 1 л"]))
    add_log = to_float(row.get("Доп. л, логистика FBS", row["Доп. л., логистика FBW"]))
else:
    coef_log = to_float(row["Коэффициент логистики, %"])
    base_log = to_float(row["Логистика за 1 л"])
    add_log = to_float(row["Доп. л., логистика FBW"])

logistics_cost = (
    base_log +
    max(volume_l - 1, 0) * add_log
) * (coef_log / 100)

# ---------- ХРАНЕНИЕ ----------
if package_type == "Короба":
    storage_base = to_float(row["Хранение за 1 л"])
    storage_add = to_float(row["Доп. л, хранение FBW"])
    coef_storage = to_float(row["Коэффициент хранения, %"])

    storage_cost = (
        storage_base +
        max(volume_l - 1, 0) * storage_add
    ) * (coef_storage / 100)

else:
    # МОНОПАЛЛЕТЫ — хранение фикс за паллету
    storage_cost = to_float(row["Хранение за 1 паллету"])

# ---------- ВЫВОД ----------
col1, col2 = st.columns(2)

with col1:
    st.metric("Логистика", f"{logistics_cost:.2f} ₽")

with col2:
    storage_label = (
        "Хранение за 1 паллету / день"
        if package_type == "Монопаллеты"
        else "Хранение за 1 шт / день"
    )
    st.metric(storage_label, f"{storage_cost:.2f} ₽")

st.divider()
st.subheader("Срок хранения")

storage_days = st.number_input(
    "На сколько дней считаем хранение?",
    min_value=0,
    max_value=365,
    value=30,
    step=5
)

# =========================
# ИТОГО ХРАНЕНИЕ ЗА ПЕРИОД
# =========================

if package_type == "Монопаллеты":
    # storage_cost = ₽ за 1 паллету / день
    storage_total = storage_cost * storage_days
    storage_unit_label = "Хранение за период (1 паллета)"

else:
    # storage_cost = ₽ за 1 шт / день
    storage_total = storage_cost * storage_days
    storage_unit_label = "Хранение за период (1 шт)"

st.metric(
    storage_unit_label,
    f"{storage_total:,.2f} ₽".replace(",", " ")
)

# =========================
# ОБРАТНАЯ ЛОГИСТИКА
# =========================

st.divider()
st.subheader("Обратная логистика (с учётом % выкупа)")

# безопасный дефолт, если % выкупа ещё не посчитан
buyout_default = avg_buyout if "avg_buyout" in locals() else 30.0

buyout_rate = st.slider(
    "Процент выкупа (%)",
    min_value=0,
    max_value=100,
    value=int(round(buyout_default)),
    step=1
) / 100

return_logistics_cost = st.number_input(
    "Стоимость обратной логистики за 1 возврат, ₽",
    min_value=0.0,
    value=50.0,
    step=5.0
)

if buyout_rate > 0:
    reverse_logistics_unit = (
        (1 - buyout_rate) / buyout_rate
    ) * return_logistics_cost
else:
    reverse_logistics_unit = 0

st.metric(
    "Обратная логистика на 1 проданную единицу",
    f"{reverse_logistics_unit:,.2f} ₽"
)

st.divider()
st.subheader("Расходы на маркетплейсе + остаток на закупку")

if result_row is None:
    st.warning("Выберите категорию WB, чтобы рассчитать экономику.")
else:
    # =========================
    # РЕКЛАМА (с учётом % выкупа)
    # =========================
    if buyout_rate > 0:
        ad_cost = (price_for_calc * ad_share / 100) / buyout_rate
    else:
        ad_cost = 0.0

    # =========================
    # КОМИССИЯ WB
    # =========================
    if supply_model == "FBW":
        wb_commission_rate = float(result_row["Склад WB, %"]) / 100
    else:
        wb_commission_rate = float(
            result_row["Склад продавца - везу на склад WB, %"]
        ) / 100

    wb_commission = price_for_calc * wb_commission_rate

    # =========================
    # ФФ ОБРАБОТКА ПО ОБЪЁМУ
    # =========================
    def ff_processing_cost_by_liters(vol_l: float) -> float:
        tiers = [
            (0.5, 15),
            (1.0, 20),
            (3.0, 30),
            (4.5, 40),
            (7.0, 65),
            (11.0, 90),
            (17.0, 111),
            (35.0, 197),
        ]

        if vol_l <= 0:
            return 0.0

        for limit, cost in tiers:
            if vol_l <= limit:
                return float(cost)

        return float(tiers[-1][1])

    unit_volume_l = (length_cm * width_cm * height_cm) / 1000.0
    ff_processing_cost = ff_processing_cost_by_liters(unit_volume_l)

    # =========================
    # ВСЕ РАСХОДЫ МАРКЕТПЛЕЙСА
    # =========================
    mp_costs_total = (
        wb_commission +
        logistics_cost +
        storage_total +
        reverse_logistics_unit +
        ff_processing_cost
    )

    # =========================
    # ЦЕЛЕВАЯ МАРЖА
    # =========================
    target_gm_rate = target_gm / 100

    # =========================
    # ОСТАТОК НА ЗАКУПКУ + ДОСТАВКУ ДО ГРАНИЦЫ
    # =========================
    china_border_budget = (
        price_for_calc * (1 - target_gm_rate)
        - mp_costs_total
        - ad_cost
    )

    # =========================
    # ВЫВОД
    # =========================
    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            "Цена для расчёта юнит-экономики (без СПП)",
            f"{price_for_calc:,.0f} ₽".replace(",", " ")
        )

    with col2:
        st.metric(
            "Остаток на себестоимость + логистику",
            f"{china_border_budget:,.2f} ₽".replace(",", " ")
        )

    # =========================
    # ДЕТАЛИ
    # =========================
    with st.expander("Расходы на маркетплейсе"):
        st.write(f"Комиссия WB: {wb_commission:,.2f} ₽".replace(",", " "))
        st.write(f"Логистика WB: {logistics_cost:,.2f} ₽".replace(",", " "))
        st.write(f"Хранение: {storage_total:,.2f} ₽".replace(",", " "))
        st.write(f"Обратная логистика: {reverse_logistics_unit:,.2f} ₽".replace(",", " "))
        st.write(f"ФФ обработка: {ff_processing_cost:,.2f} ₽".replace(",", " "))
        st.write(f"Реклама: {ad_cost:,.2f} ₽".replace(",", " "))
        st.write(f"Целевая валовая рентабельность: {target_gm:.1f} %")

# =========================
# КОЛИЧЕСТВО В ПАРТИИ + ОБЪЁМ ПАРТИИ
# =========================

st.divider()
st.subheader("Партия (количество)")

# 1) количество в партии (шт)
qty_units = st.number_input(
    "Количество в партии, шт",
    min_value=1,
    step=10,
    value=100  # <-- дефолт, поменяй как нужно
)

# =========================
# ДОСТАВКА ИЗ КИТАЯ (ЧИСТАЯ ПОСТАВКА) — НА 1 ЕДИНИЦУ
# =========================

import requests
import xml.etree.ElementTree as ET

st.divider()
st.subheader("Доставка из Китая (чистая поставка)")

# -------------------------
# БАЗОВЫЕ РАСЧЁТЫ (СКРЫТЫ)
# -------------------------
with st.expander("Показать детали расчёта логистики"):

    # Количество в партии
    if "qty_units" not in locals():
        qty_units = st.number_input(
            "Количество в партии, шт",
            min_value=1,
            step=10,
            value=100
        )

    # Объёмы
    unit_volume_m3 = (length_cm / 100) * (width_cm / 100) * (height_cm / 100)
    batch_volume_m3 = unit_volume_m3 * qty_units
    container_m3 = 66.0
    share_in_container = batch_volume_m3 / container_m3 if container_m3 > 0 else 0.0

    colv1, colv2, colv3 = st.columns(3)
    with colv1:
        st.metric("Объём 1 шт", f"{unit_volume_m3:.6f} м³")
    with colv2:
        st.metric("Объём партии", f"{batch_volume_m3:.3f} м³")
    with colv3:
        st.metric("Доля контейнера (66 м³)", f"{share_in_container:.2%}")

    st.markdown("### Курс USD → RUB")

    def get_usd_rub_cbr():
        try:
            resp = requests.get(
                "https://www.cbr.ru/scripts/XML_daily.asp",
                timeout=6
            )
            resp.raise_for_status()
            root = ET.fromstring(resp.content)

            for valute in root.findall("Valute"):
                if valute.findtext("CharCode") == "USD":
                    nominal = float(valute.findtext("Nominal").replace(",", "."))
                    value = float(valute.findtext("Value").replace(",", "."))
                    return value / nominal
        except Exception:
            return None

    auto_usd_rub = get_usd_rub_cbr()

    use_auto_fx = st.checkbox(
        "Использовать авто-курс ЦБ РФ",
        value=True if auto_usd_rub else False
    )

    usd_rub = st.number_input(
        "Курс USD → RUB",
        min_value=0.0,
        value=float(round(auto_usd_rub, 2)) if (use_auto_fx and auto_usd_rub) else 95.0,
        step=0.1
    )

    # Расходы на контейнер
    st.markdown("### Расходы на контейнер")

    freight_usd = st.number_input("Фрахт, $", value=5040.0, step=10.0)
    broker_rub = st.number_input("Брокер, ₽", value=16800.0, step=100.0)
    ru_delivery_rub = st.number_input("Доставка по РФ, ₽", value=74000.0, step=100.0)
    loaders_rub = st.number_input("Грузчики, ₽", value=12000.0, step=100.0)
    repack_rub = st.number_input("Переупаковка, ₽", value=33000.0, step=100.0)

    freight_rub = freight_usd * usd_rub

    container_total_rub = (
        freight_rub +
        broker_rub +
        ru_delivery_rub +
        loaders_rub +
        repack_rub
    )

    allocated_party_rub = container_total_rub * share_in_container
    logistics_per_unit_rub = allocated_party_rub / qty_units if qty_units > 0 else 0.0

    st.markdown("### Итоги")
    st.write(f"Итого по контейнеру: {container_total_rub:,.0f} ₽".replace(",", " "))
    st.write(f"Доля расходов партии: {allocated_party_rub:,.0f} ₽".replace(",", " "))

# -------------------------
# ГЛАВНАЯ ЦИФРА (ВСЕГДА ВИДНА)
# -------------------------

st.metric(
    "Логистика (чистая поставка) на 1 шт",
    f"{logistics_per_unit_rub:,.2f} ₽".replace(",", " ")
)

# =========================
# СКРЫТЫЙ РАСЧЁТ СЕБЕСТОИМОСТИ (нужен для best_price)
# =========================

# qty_units
if "qty_units" not in locals():
    qty_units = 100

# защита
if "china_border_budget" not in locals() or "logistics_per_unit_rub" not in locals():
    st.stop()

budget_goods_plus_customs = china_border_budget - logistics_per_unit_rub

customs_fee_total_fixed = 2000.0  # ₽ за партию

def customs_per_unit_for_price(unit_price: float) -> float:
    total_goods_value = unit_price * qty_units
    duty_total = total_goods_value * 0.05
    vat_total = (total_goods_value + duty_total + customs_fee_total_fixed) * 0.22
    return (customs_fee_total_fixed + duty_total + vat_total) / qty_units

low, high = 0.0, max(budget_goods_plus_customs, 0.0)
best_price = 0.0

for _ in range(60):
    mid = (low + high) / 2
    if mid + customs_per_unit_for_price(mid) <= budget_goods_plus_customs:
        best_price = mid
        low = mid
    else:
        high = mid

# =========================
# ПЕРЕВОД СЕБЕСТОИМОСТИ В ЮАНИ (CNY)
# =========================

st.divider()
st.subheader("Максимальная цена закупки в юанях (чистая поставка)")

import requests
import xml.etree.ElementTree as ET

def get_cny_rub_cbr():
    """
    Возвращает курс CNY→RUB по ЦБ РФ
    """
    try:
        resp = requests.get(
            "https://www.cbr.ru/scripts/XML_daily.asp",
            timeout=6
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        for valute in root.findall("Valute"):
            if valute.findtext("CharCode") == "CNY":
                nominal = float(valute.findtext("Nominal").replace(",", "."))
                value = float(valute.findtext("Value").replace(",", "."))
                return value / nominal
    except Exception:
        return None

auto_cny_rub = get_cny_rub_cbr()

colfx1, colfx2 = st.columns(2)

with colfx1:
    use_auto_cny = st.checkbox(
        "Использовать авто-курс CNY (ЦБ РФ)",
        value=True if auto_cny_rub else False,
        key="use_auto_cny"
    )

with colfx2:
    cny_rub_manual = st.number_input(
        "Курс CNY → RUB (вручную)",
        min_value=0.0,
        value=float(round(auto_cny_rub, 2)) if auto_cny_rub else 13.0,
        step=0.01,
        key="cny_rub_manual"
    )

cny_rub = auto_cny_rub if (use_auto_cny and auto_cny_rub) else cny_rub_manual

# себестоимость в юанях
cost_cny = best_price / cny_rub if cny_rub > 0 else 0.0

col1, col2 = st.columns(2)

with col1:
    st.metric(
        "Себестоимость, ₽ / шт",
        f"{best_price:,.2f} ₽".replace(",", " ")
    )

with col2:
    st.metric(
        "Себестоимость, ¥ / шт",
        f"{cost_cny:,.2f} ¥".replace(",", " ")
    )

# =========================
# ДОСТАВКА ИЗ КИТАЯ — КАРГО (ТОЛЬКО ПО ВЕСУ)
# =========================

st.divider()
col = st.columns(1)[0]
with col:
    st.subheader("Доставка из Китая (карго)")

    import requests
    import xml.etree.ElementTree as ET

    # --- курс USD → RUB (ЦБ РФ) ---
    def get_usd_rub_cbr():
        try:
            resp = requests.get(
                "https://www.cbr.ru/scripts/XML_daily.asp",
                timeout=6
            )
            resp.raise_for_status()
            root = ET.fromstring(resp.content)

            for valute in root.findall("Valute"):
                if valute.findtext("CharCode") == "USD":
                    nominal = float(valute.findtext("Nominal").replace(",", "."))
                    value = float(valute.findtext("Value").replace(",", "."))
                    return value / nominal
        except Exception:
            return None

    usd_rub = get_usd_rub_cbr() or 95.0

    # --- ставка карго ---
    cargo_rate_usd_per_kg = 2.7  # $ / кг

    # --- РАСЧЁТ ---
    # weight_kg должен быть уже задан в блоке "Габариты и объём"
    logistics_per_unit_rub = weight_kg * cargo_rate_usd_per_kg * usd_rub

    # --- ВЫВОД ---
    st.metric(
        "Логистика (карго) на 1 шт",
        f"{logistics_per_unit_rub:,.2f} ₽".replace(",", " ")
    )

# =========================
# МАКСИМАЛЬНАЯ ЦЕНА ЗАКУПКИ — КАРГО (ПРОСТО И ПРАВИЛЬНО)
# =========================

st.divider()
st.subheader("Максимальная цена закупки в юанях (карго)")

# защита
if "china_border_budget" not in locals() or "logistics_per_unit_rub" not in locals():
    st.warning("Не хватает данных для расчёта карго")
    st.stop()

# 1️⃣ себестоимость в рублях (карго)
max_cost_rub_cargo = china_border_budget - logistics_per_unit_rub

# если ушли в минус — фиксируем
max_cost_rub_cargo = max(max_cost_rub_cargo, 0.0)

# 2️⃣ курс CNY → RUB
import requests
import xml.etree.ElementTree as ET

def get_cny_rub_cbr():
    try:
        resp = requests.get(
            "https://www.cbr.ru/scripts/XML_daily.asp",
            timeout=6
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        for valute in root.findall("Valute"):
            if valute.findtext("CharCode") == "CNY":
                nominal = float(valute.findtext("Nominal").replace(",", "."))
                value = float(valute.findtext("Value").replace(",", "."))
                return value / nominal
    except Exception:
        return None

cny_rub = get_cny_rub_cbr() or 13.0

# 3️⃣ себестоимость в юанях
max_cost_cny_cargo = max_cost_rub_cargo / cny_rub if cny_rub > 0 else 0.0

# 4️⃣ вывод
col1, col2 = st.columns(2)

with col1:
    st.metric(
        "Себестоимость, ₽ / шт",
        f"{max_cost_rub_cargo:,.2f} ₽".replace(",", " ")
    )

with col2:
    st.metric(
        "Себестоимость, ¥ / шт",
        f"{max_cost_cny_cargo:,.2f} ¥".replace(",", " ")
    )