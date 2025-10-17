import sys
import sqlite3
import traceback
from datetime import datetime, timedelta
from PyQt6 import QtCore, QtWidgets, QtGui
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import QFileDialog

DB_NAME = "customers.db"

QSS = """
QWidget { background: #121212; color: #e0e0e0; font-family: 'Segoe UI', Roboto, Arial; font-size: 11pt; }
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDateEdit, QDateTimeEdit, QDoubleSpinBox { background: #1e1e1e; border: 1px solid #2b2b2b; padding: 6px; }
QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #2a7bd6, stop:1 #155fa6); border-radius:10px; padding:8px; }
QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #3b8be6, stop:1 #1d6fb5); }
QTableWidget { gridline-color: #2b2b2b; }
QHeaderView::section { background: #1f1f1f; padding: 6px; border: 1px solid #2b2b2b; }
QTableWidget::item:selected { background: #2a7bd6; color: #fff; }
QLabel#title { font-size: 16pt; font-weight: bold; }
QTabWidget::pane { border: 1px solid #2b2b2b; }
QTabBar::tab { padding: 8px; background: #1e1e1e; }
QTabBar::tab:selected { background: #2a7bd6; }
QGroupBox { border: 1px solid #2b2b2b; margin-top: 10px; padding-top: 15px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; }
"""

class Database:
    def __init__(self, db_path=DB_NAME):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            tc_no TEXT UNIQUE,
            phone TEXT UNIQUE,
            address TEXT,
            notes TEXT,
            debt REAL DEFAULT 0
        )""")

        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            transaction_type TEXT NOT NULL,
            payment_type TEXT NOT NULL,
            date TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers (id)
        )""")
        self.conn.commit()

    def add_customer(self, first_name, last_name, tc_no, phone, address, notes, debt):
        # normalize empty strings to None so UNIQUE columns allow multiple NULLs
        tc_no_db = tc_no.strip() if tc_no and tc_no.strip() else None
        phone_db = phone.strip() if phone and phone.strip() else None
        self.conn.execute(
            "INSERT INTO customers (first_name, last_name, tc_no, phone, address, notes, debt) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (first_name, last_name, tc_no_db, phone_db, address, notes, float(debt)))
        self.conn.commit()

    def update_customer(self, cust_id, first_name, last_name, tc_no, phone, address, notes, debt):
        tc_no_db = tc_no.strip() if tc_no and tc_no.strip() else None
        phone_db = phone.strip() if phone and phone.strip() else None
        self.conn.execute(
            "UPDATE customers SET first_name=?, last_name=?, tc_no=?, phone=?, address=?, notes=?, debt=? WHERE id=?",
            (first_name, last_name, tc_no_db, phone_db, address, notes, float(debt), cust_id))
        self.conn.commit()

    def delete_customer(self, cust_id):
        self.conn.execute("DELETE FROM customers WHERE id=?", (cust_id,))
        self.conn.commit()

    def list_customers(self, filter_text=None):
        cur = self.conn.cursor()
        if filter_text:
            like = f"%{filter_text}%"
            cur.execute("""
                SELECT id, first_name, last_name, tc_no, phone, address, notes, debt 
                FROM customers 
                WHERE first_name LIKE ? OR last_name LIKE ? OR phone LIKE ? OR tc_no LIKE ?
                ORDER BY last_name, first_name
            """, (like, like, like, like))
        else:
            cur.execute("""
                SELECT id, first_name, last_name, tc_no, phone, address, notes, debt 
                FROM customers 
                ORDER BY last_name, first_name
            """)
        return cur.fetchall()

    def get_total_debt(self):
        cur = self.conn.cursor()
        cur.execute("SELECT SUM(debt) FROM customers")
        result = cur.fetchone()
        return float(result[0]) if result and result[0] is not None else 0.0

    def add_transaction(self, customer_id, amount, description, transaction_type, payment_type, date=None):
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            try:
                datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
            except Exception:
                try:
                    dt = datetime.strptime(date, "%Y-%m-%d")
                    date = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.conn.execute(
            "INSERT INTO transactions (customer_id, amount, description, transaction_type, payment_type, date) VALUES (?, ?, ?, ?, ?, ?)",
            (customer_id, float(amount), description, transaction_type, payment_type, date))
        self.conn.commit()

        # Update customer's debt: income reduces debt, expense increases
        if transaction_type == 'income':
            change = -abs(float(amount))
        else:
            change = abs(float(amount))

        self.conn.execute(
            "UPDATE customers SET debt = debt + ? WHERE id = ?",
            (change, customer_id))
        self.conn.commit()

    def delete_transaction(self, transaction_id):
        cur = self.conn.cursor()
        cur.execute("SELECT customer_id, amount, transaction_type FROM transactions WHERE id=?", (transaction_id,))
        transaction = cur.fetchone()

        if transaction:
            customer_id, amount, transaction_type = transaction

            if transaction_type == 'income':
                change = amount  # reverse income -> add back
            else:
                change = -amount  # reverse expense -> subtract

            self.conn.execute(
                "UPDATE customers SET debt = debt + ? WHERE id = ?",
                (change, customer_id))

            self.conn.execute("DELETE FROM transactions WHERE id=?", (transaction_id,))
            self.conn.commit()
            return True
        return False

    def update_transaction(self, transaction_id, amount, description, transaction_type, payment_type, date=None):
        cur = self.conn.cursor()
        cur.execute("SELECT customer_id, amount, transaction_type FROM transactions WHERE id=?", (transaction_id,))
        old = cur.fetchone()
        if not old:
            return False
        customer_id, old_amount, old_type = old

        if old_type == 'income':
            old_change = float(old_amount)
        else:
            old_change = -float(old_amount)

        if transaction_type == 'income':
            new_change = -abs(float(amount))
        else:
            new_change = abs(float(amount))

        net = old_change + new_change

        self.conn.execute("UPDATE customers SET debt = debt + ? WHERE id = ?", (net, customer_id))

        if date is None:
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            try:
                datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
                date_str = date
            except Exception:
                try:
                    dt = datetime.strptime(date, "%Y-%m-%d")
                    date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.conn.execute(
            "UPDATE transactions SET amount=?, description=?, transaction_type=?, payment_type=?, date=? WHERE id=?",
            (float(amount), description, transaction_type, payment_type, date_str, transaction_id))
        self.conn.commit()
        return True

    def get_transactions(self, customer_id):
        cur = self.conn.cursor()
        cur.execute("""
            SELECT id, amount, description, transaction_type, payment_type, date 
            FROM transactions 
            WHERE customer_id = ?
            ORDER BY date DESC
        """, (customer_id,))
        return cur.fetchall()

    def get_transaction_stats(self, customer_id):
        cur = self.conn.cursor()

        cur.execute("""
            SELECT 
                SUM(CASE WHEN transaction_type='income' THEN amount ELSE 0 END) as total_income,
                SUM(CASE WHEN transaction_type='expense' THEN amount ELSE 0 END) as total_expense
            FROM transactions 
            WHERE customer_id=?
        """, (customer_id,))
        stats = cur.fetchone()

        date_30_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        cur.execute("""
            SELECT 
                SUM(CASE WHEN transaction_type='income' THEN amount ELSE 0 END) as monthly_income,
                SUM(CASE WHEN transaction_type='expense' THEN amount ELSE 0 END) as monthly_expense
            FROM transactions 
            WHERE customer_id=? AND date >= ?
        """, (customer_id, date_30_days_ago))
        monthly_stats = cur.fetchone()

        return {
            'total_paid': stats[0] or 0,
            'total_debt': stats[1] or 0,
            'monthly_paid': monthly_stats[0] or 0,
            'monthly_debt': monthly_stats[1] or 0
        }

class CustomerDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, customer=None):
        super().__init__(parent)
        self.setWindowTitle("Müşteri Bilgileri")
        self.resize(480, 350)
        layout = QtWidgets.QFormLayout(self)

        self.first = QtWidgets.QLineEdit()
        self.last = QtWidgets.QLineEdit()
        self.tc_no = QtWidgets.QLineEdit()
        self.tc_no.setInputMask("99999999999;_")
        self.phone = QtWidgets.QLineEdit()
        self.address = QtWidgets.QTextEdit()
        self.notes = QtWidgets.QTextEdit()
        self.debt = QtWidgets.QDoubleSpinBox()
        self.debt.setMaximum(1e9)
        self.debt.setPrefix("₺ ")

        layout.addRow("Ad:", self.first)
        layout.addRow("Soyad:", self.last)
        layout.addRow("TC Kimlik No:", self.tc_no)
        layout.addRow("Telefon:", self.phone)
        layout.addRow("Adres:", self.address)
        layout.addRow("Notlar:", self.notes)
        layout.addRow("Borç:", self.debt)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

        if customer:
            self.first.setText(customer.get('first_name', ''))
            self.last.setText(customer.get('last_name', ''))
            if customer.get('tc_no'):
                self.tc_no.setText(str(customer.get('tc_no')))
            self.phone.setText(customer.get('phone', ''))
            self.address.setPlainText(customer.get('address', ''))
            self.notes.setPlainText(customer.get('notes', ''))
            self.debt.setValue(customer.get('debt', 0))

    def get_data(self):
        return {
            'first_name': self.first.text().strip(),
            'last_name': self.last.text().strip(),
            'tc_no': self.tc_no.text().strip(),
            'phone': self.phone.text().strip(),
            'address': self.address.toPlainText().strip(),
            'notes': self.notes.toPlainText().strip(),
            'debt': self.debt.value()
        }

class TransactionDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, customer_id=None, transaction=None):
        super().__init__(parent)
        self.setWindowTitle("Hareket Düzenle" if transaction else "Hareket Ekle")
        self.customer_id = customer_id
        self.transaction = transaction
        self.resize(420, 380)

        layout = QtWidgets.QFormLayout(self)

        self.amount = QtWidgets.QDoubleSpinBox()
        self.amount.setMaximum(1e9)
        self.amount.setPrefix("₺ ")

        self.transaction_type = QtWidgets.QComboBox()
        self.transaction_type.addItems(["Borç Ekle (Çıkış)", "Ödeme Al (Giriş)"])

        self.payment_type = QtWidgets.QComboBox()
        self.payment_type.addItems(["Nakit", "Kart"])

        self.description = QtWidgets.QTextEdit()
        self.description.setMaximumHeight(100)

        self.date_edit = QtWidgets.QDateTimeEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.date_edit.setDateTime(QtCore.QDateTime.currentDateTime())

        layout.addRow("Tutar:", self.amount)
        layout.addRow("İşlem Türü:", self.transaction_type)
        layout.addRow("Ödeme Türü:", self.payment_type)
        layout.addRow("Tarih:", self.date_edit)
        layout.addRow("Açıklama:", self.description)

        if transaction:
            self.amount.setValue(float(transaction.get('amount', 0)))
            # stored in DB as 'expense' or 'income'
            self.transaction_type.setCurrentIndex(0 if transaction.get('transaction_type') == 'expense' else 1)
            self.payment_type.setCurrentIndex(0 if transaction.get('payment_type') == 'cash' else 1)
            self.description.setPlainText(transaction.get('description', ''))
            try:
                dt = datetime.strptime(transaction.get('date', ''), "%Y-%m-%d %H:%M:%S")
                self.date_edit.setDateTime(QtCore.QDateTime(dt))
            except Exception:
                pass

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def get_data(self):
        date_str = self.date_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss")
        return {
            'amount': self.amount.value(),
            'description': self.description.toPlainText().strip(),
            'transaction_type': 'income' if self.transaction_type.currentIndex() == 1 else 'expense',
            'payment_type': 'cash' if self.payment_type.currentIndex() == 0 else 'card',
            'date': date_str
        }

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.setWindowTitle("Sigorta - Müşteri ve Muhasebe Takip")
        self.resize(1100, 700)
        self.current_customer_id = None

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central)

        self.tabs = QtWidgets.QTabWidget()
        main_layout.addWidget(self.tabs)

        self.setup_customer_tab()
        self.setup_transactions_tab(None)

        self.setStyleSheet(QSS)
        self.reload_table()

    def setup_customer_tab(self):
        customer_tab = QtWidgets.QWidget()
        self.tabs.addTab(customer_tab, "Müşteriler")

        vbox = QtWidgets.QVBoxLayout(customer_tab)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Müşteri Takip Sistemi")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("İsim, telefon veya TC no ile ara...")
        self.search.returnPressed.connect(self.reload_table)
        header.addWidget(self.search)
        vbox.addLayout(header)

        self.table = QtWidgets.QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["ID", "Ad", "Soyad", "TC No", "Telefon", "Adres", "Notlar", "Borç (₺)"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)  # type: ignore
        self.table.setColumnHidden(0, True)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(6, 200)
        self.table.itemSelectionChanged.connect(self.load_transactions)
        vbox.addWidget(self.table)

        btns = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("Yeni Müşteri")
        add_btn.clicked.connect(self.add_customer)
        edit_btn = QtWidgets.QPushButton("Düzenle")
        edit_btn.clicked.connect(self.edit_customer)
        del_btn = QtWidgets.QPushButton("Sil")
        del_btn.clicked.connect(self.delete_customer)
        self.transaction_btn = QtWidgets.QPushButton("Hareket Ekle")
        self.transaction_btn.clicked.connect(self.add_transaction)
        self.transaction_btn.setEnabled(False)
        refresh_btn = QtWidgets.QPushButton("Yenile")
        refresh_btn.clicked.connect(self.reload_table)

        btns.addWidget(add_btn)
        btns.addWidget(edit_btn)
        btns.addWidget(del_btn)
        btns.addWidget(self.transaction_btn)
        btns.addStretch()
        btns.addWidget(refresh_btn)
        vbox.addLayout(btns)

        self.statusbar = QtWidgets.QStatusBar()
        self.setStatusBar(self.statusbar)
        self.total_label = QtWidgets.QLabel()
        self.statusbar.addPermanentWidget(self.total_label)

    def setup_transactions_tab(self, customer_id=None):
        # rebuild transactions tab every çağrıldığında (clean)
        self.transactions_tab = QtWidgets.QWidget()
        if self.tabs.count() > 1:
            self.tabs.removeTab(1)
        self.tabs.addTab(self.transactions_tab, "Hareketler")

        layout = QtWidgets.QVBoxLayout(self.transactions_tab)

        # --- Müşteri seçim ve arama (tek defa tanımlanır)
        customer_group = QtWidgets.QGroupBox("Müşteri Seçimi")
        customer_layout = QtWidgets.QGridLayout()

        self.customer_combo = QtWidgets.QComboBox()
        self.customer_combo.setMinimumWidth(300)
        self.refresh_customer_combo()

        


        customer_layout.addWidget(QtWidgets.QLabel("Ara:"), 1, 0)
        self.customer_search = QtWidgets.QLineEdit()
        self.customer_search.setPlaceholderText("İsim, TC veya telefon ile ara...")
        self.customer_search.textChanged.connect(self.update_search_results)
        customer_layout.addWidget(self.customer_search, 1, 1)
        
        self.search_results = QtWidgets.QListWidget()
        self.search_results.setMaximumHeight(150)
        self.search_results.setVisible(False)
        self.search_results.itemClicked.connect(self.select_customer_from_list)
        customer_layout.addWidget(self.search_results, 2, 0, 1, 3)

        refresh_btn = QtWidgets.QPushButton("Yenile")
        refresh_btn.clicked.connect(self.refresh_customer_combo)

        customer_layout.addWidget(QtWidgets.QLabel("Müşteri:"), 0, 0)
        customer_layout.addWidget(self.customer_combo, 0, 1)
        customer_layout.addWidget(QtWidgets.QLabel("Ara:"), 1, 0)
        customer_layout.addWidget(self.customer_search, 1, 1)
        customer_layout.addWidget(refresh_btn, 0, 2, 2, 1)

        customer_group.setLayout(customer_layout)
        layout.addWidget(customer_group)

        self.customer_combo.currentIndexChanged.connect(self.customer_selection_changed)

        # --- Filtreleme
        filter_group = QtWidgets.QGroupBox("Filtreleme")
        filter_layout = QtWidgets.QHBoxLayout()

        self.filter_type = QtWidgets.QComboBox()
        self.filter_type.addItems(["Tümü", "Ödemeler", "Borçlar"])

        self.filter_payment = QtWidgets.QComboBox()
        self.filter_payment.addItems(["Tümü", "Nakit", "Kart"])

        self.filter_start_date = QtWidgets.QDateEdit()
        self.filter_start_date.setDisplayFormat("dd.MM.yyyy")
        self.filter_start_date.setDate(QtCore.QDate.currentDate().addMonths(-1))

        self.filter_end_date = QtWidgets.QDateEdit()
        self.filter_end_date.setDisplayFormat("dd.MM.yyyy")
        self.filter_end_date.setDate(QtCore.QDate.currentDate())

        filter_btn = QtWidgets.QPushButton("Filtrele")
        filter_btn.clicked.connect(self.apply_filters)

        filter_layout.addWidget(QtWidgets.QLabel("Tür:"))
        filter_layout.addWidget(self.filter_type)
        filter_layout.addWidget(QtWidgets.QLabel("Ödeme:"))
        filter_layout.addWidget(self.filter_payment)
        filter_layout.addWidget(QtWidgets.QLabel("Başlangıç:"))
        filter_layout.addWidget(self.filter_start_date)
        filter_layout.addWidget(QtWidgets.QLabel("Bitiş:"))
        filter_layout.addWidget(self.filter_end_date)
        filter_layout.addWidget(filter_btn)
        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)

        # --- İstatistikler
        stats_group = QtWidgets.QGroupBox("İstatistikler")
        stats_layout = QtWidgets.QGridLayout()

        self.total_paid_label = QtWidgets.QLabel("₺ 0.00")
        self.total_debt_label = QtWidgets.QLabel("₺ 0.00")
        self.monthly_paid_label = QtWidgets.QLabel("₺ 0.00")
        self.monthly_debt_label = QtWidgets.QLabel("₺ 0.00")
        self.difference_label = QtWidgets.QLabel("₺ 0.00")
        self.difference_label.setStyleSheet("font-weight: bold; color: #2a7bd6;")
    
        stats_layout.addWidget(QtWidgets.QLabel("Net Bakiye:"), 2, 0)
        stats_layout.addWidget(self.difference_label, 2, 1)

        stats_layout.addWidget(QtWidgets.QLabel("Toplam Ödeme:"), 0, 0)
        stats_layout.addWidget(self.total_paid_label, 0, 1)
        stats_layout.addWidget(QtWidgets.QLabel("Toplam Borç:"), 1, 0)
        stats_layout.addWidget(self.total_debt_label, 1, 1)
        stats_layout.addWidget(QtWidgets.QLabel("Son 30 Gün Ödeme:"), 0, 2)
        stats_layout.addWidget(self.monthly_paid_label, 0, 3)
        stats_layout.addWidget(QtWidgets.QLabel("Son 30 Gün Borç:"), 1, 2)
        stats_layout.addWidget(self.monthly_debt_label, 1, 3)

        export_btn = QtWidgets.QPushButton("Dışa Aktar")
        export_btn.clicked.connect(self.show_export_menu)
        stats_layout.addWidget(export_btn, 1, 4)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        # --- Hareket tablosu (müşteri sütunu eklendi)
        self.transaction_table = QtWidgets.QTableWidget(0, 8)
        self.transaction_table.setHorizontalHeaderLabels(["ID", "Tutar", "Açıklama", "Tür", "Ödeme", "Tarih", "Müşteri", ""])
        self.transaction_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.transaction_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.transaction_table.verticalHeader().setVisible(False)  # type: ignore
        self.transaction_table.setColumnHidden(0, True)
        self.transaction_table.setColumnWidth(1, 120)
        self.transaction_table.setColumnWidth(3, 100)
        self.transaction_table.setColumnWidth(4, 80)
        self.transaction_table.setColumnWidth(5, 150)
        self.transaction_table.setColumnWidth(6, 200)
        self.transaction_table.setColumnWidth(7, 160)

        layout.addWidget(self.transaction_table)

        if customer_id:
            self.load_transactions_data(customer_id)
        else:
            self.load_all_transactions()

    def show_export_menu(self):
        menu = QtWidgets.QMenu(self)
        
        pdf_action = QtGui.QAction("PDF Olarak Kaydet", self)
        pdf_action.triggered.connect(self.export_to_pdf)
        menu.addAction(pdf_action)
        
        menu.exec(QtGui.QCursor.pos())

    def export_to_pdf(self):
        if not self.current_customer_id:
            QtWidgets.QMessageBox.warning(self, "Uyarı", "Lütfen önce bir müşteri seçin!")
            return

        # Müşteri bilgilerini al
        customer = self.db.conn.execute(
            "SELECT first_name, last_name, phone FROM customers WHERE id=?", 
            (self.current_customer_id,)
        ).fetchone()
        
        if not customer:
            QtWidgets.QMessageBox.warning(self, "Hata", "Müşteri bilgileri alınamadı!")
            return
        
        # Hareketleri al
        transactions = self.db.get_transactions(self.current_customer_id)

        stats = self.db.get_transaction_stats(self.current_customer_id)
        total_paid = stats['total_paid']
        total_debt = stats['total_debt']
        difference = total_paid - total_debt
        
        # HTML içeriği oluştur
        html = f"""
        <h1>{customer[0]} {customer[1]} - Hareket Dökümü</h1>
        <br>
        <table border="1" cellpadding="5" width="100%">
            <tr>
                <th>Tarih</th>
                <th>Tür</th>
                <th>Tutar</th>
                <th>Açıklama</th>
                <th>Ödeme Türü</th>
            </tr>
        """
        
        for t in transactions:
            html += f"""
            <tr>
                <td>{t[5]}</td>
                <td>{'Ödeme' if t[3]=='income' else 'Borç'}</td>
                <td>{t[1]:.2f} ₺</td>
                <td>{t[2] or ''}</td>
                <td>{'Nakit' if t[4]=='cash' else 'Kart'}</td>
            </tr>
            """
        
        html += f"""
        
        </table>

        <div style="margin-top: 30px; text-align: right;">
            <table style="width: 300px; float: right; border: 1px solid #ddd;">
                <tr>
                    <td style="padding: 8px;"><strong>Toplam Ödeme:</strong></td>
                    <td style="padding: 8px; text-align: right;">₺ {total_paid:,.2f}</td>
                </tr>
                <tr>
                    <td style="padding: 8px;"><strong>Toplam Borç:</strong></td>
                    <td style="padding: 8px; text-align: right;">₺ {total_debt:,.2f}</td>
                </tr>
                <tr>
                    <td style="padding: 8px;"><strong>Net Bakiye:</strong></td>
                    <td style="padding: 8px; text-align: right; { 'color: green;' if difference >=0 else 'color: red;' }">
                        ₺ {abs(difference):,.2f} ({'Alacak' if difference >=0 else 'Borç'})
                    </td>
                </tr>
            </table>
        </div>

        """
        # Kullanıcıya kaydetme yeri soralım
        default_filename = f"{customer[0]}_{customer[1]}_hareketler.pdf"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "PDF Olarak Kaydet",
            default_filename,
            "PDF Dosyaları (*.pdf);;Tüm Dosyalar (*)"
        )
        
        if not file_path:  # Kullanıcı iptal etti
            return
        
        # Dosya uzantısı kontrolü
        if not file_path.lower().endswith('.pdf'):
            file_path += '.pdf'
        
        # PDF'e yazdır
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(file_path)
        
        doc = QTextDocument()
        doc.setHtml(html)
        doc.print(printer)
        
        # Kaydedilen yeri göster
        QtWidgets.QMessageBox.information(
            self,
            "Başarılı",
            f"PDF oluşturuldu!\n\nKaydedilen konum:\n{file_path}"
        )
    
    def update_search_results(self, text):
        """Arama kutusuna yazıldıkça müşteri listesini günceller"""
        search_text = text.strip()
        if not search_text:
            self.search_results.clear()
            self.search_results.setVisible(False)
            return
        
        self.search_results.clear()
        customers = self.db.list_customers(search_text)
        
        for customer in customers:
            item = QtWidgets.QListWidgetItem(f"{customer[1]} {customer[2]} - {customer[3] or ''}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, customer[0])  # ID'yi sakla
            self.search_results.addItem(item)
        
        self.search_results.setVisible(bool(customers))

    def select_customer_from_list(self, item):
        """Listeden seçilen müşteriyi yükler"""
        customer_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if customer_id:
            self.current_customer_id = customer_id
            self.customer_search.clear()
            self.search_results.clear()
            self.search_results.setVisible(False)
            self.load_transactions_data(customer_id)
            # Müşteri combobox'ında seçili hale getir
            self.select_customer_in_combo(customer_id)

    def filter_customers(self):
        search_text = self.customer_search.text().strip().lower()
        self.customer_combo.clear()

        if not search_text:
            self.refresh_customer_combo()
            return

        customers = self.db.list_customers()
        found = False
        self.customer_combo.addItem("Tüm Müşteriler", None)

        for customer in customers:
            first = (customer[1] or "").lower()
            last = (customer[2] or "").lower()
            tc = (customer[3] or "").lower()
            phone = (customer[4] or "").lower()

            if search_text in first or search_text in last or search_text in tc or search_text in phone:
                display_text = f"{customer[1]} {customer[2]} ({customer[4] or ''})"
                self.customer_combo.addItem(display_text, customer[0])
                found = True

        if not found:
            self.customer_combo.addItem("Müşteri bulunamadı", -1)

    def refresh_customer_combo(self):
        self.customer_combo.clear()
        self.customer_combo.addItem("Tüm Müşteriler", None)
        customers = self.db.list_customers()
        for customer in customers:
            display_text = f"{customer[1]} {customer[2]}"
            self.customer_combo.addItem(display_text, customer[0])

    def select_customer_in_combo(self, customer_id):
        for i in range(self.customer_combo.count()):
            if self.customer_combo.itemData(i) == customer_id:
                self.customer_combo.setCurrentIndex(i)
                break

    def customer_selection_changed(self, index):
        selected_customer_id = self.customer_combo.itemData(index)
        if selected_customer_id == -1:  # "Müşteri bulunamadı"
            self.transaction_table.setRowCount(0)
            return

        if selected_customer_id:
            self.load_transactions_data(selected_customer_id)
        else:
            self.load_all_transactions()

    def load_all_transactions(self, filters=None):
        # Tüm müşterilerin hareketlerini tabloya yükle
        query = """
            SELECT t.id, t.amount, t.description, t.transaction_type, t.payment_type, t.date, 
                c.first_name || ' ' || c.last_name as customer_name
            FROM transactions t
            JOIN customers c ON t.customer_id = c.id
            ORDER BY t.date DESC
        """
        try:
            transactions = self.db.conn.cursor().execute(query).fetchall()
        except Exception:
            transactions = []
            print("load_all_transactions hata:\n", traceback.format_exc())

        self.transaction_table.setRowCount(0)

        for row in transactions:
            # row: (id, amount, description, transaction_type, payment_type, date, customer_name)
            # apply filters if present
            try:
                trans_date = None
                try:
                    trans_date = datetime.strptime(row[5], "%Y-%m-%d %H:%M:%S").date()
                except Exception:
                    try:
                        trans_date = datetime.strptime(row[5], "%Y-%m-%d").date()
                    except Exception:
                        trans_date = None

                if filters:
                    if (filters.get('start_date') and trans_date and trans_date < filters['start_date']) or \
                       (filters.get('end_date') and trans_date and trans_date > filters['end_date']):
                        continue

                    if filters.get('type') == 'income' and row[3] != 'income':
                        continue
                    if filters.get('type') == 'expense' and row[3] != 'expense':
                        continue
                    if filters.get('payment') and filters['payment'] != row[4]:
                        continue

                row_pos = self.transaction_table.rowCount()
                self.transaction_table.insertRow(row_pos)

                transaction_type = "Ödeme" if row[3] == 'income' else "Borç"
                payment_type = "Nakit" if row[4] == 'cash' else "Kart"
                color = QtGui.QColor(76, 175, 80) if row[3] == 'income' else QtGui.QColor(244, 67, 54)

                # ID
                id_item = QtWidgets.QTableWidgetItem(str(row[0]))
                self.transaction_table.setItem(row_pos, 0, id_item)

                # Tutar
                amt_item = QtWidgets.QTableWidgetItem(f"₺ {abs(float(row[1])):,.2f}")
                amt_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
                amt_item.setForeground(color)
                self.transaction_table.setItem(row_pos, 1, amt_item)

                # Açıklama
                desc_item = QtWidgets.QTableWidgetItem(row[2] or "")
                self.transaction_table.setItem(row_pos, 2, desc_item)

                # Tür
                type_item = QtWidgets.QTableWidgetItem(transaction_type)
                type_item.setForeground(color)
                self.transaction_table.setItem(row_pos, 3, type_item)

                # Ödeme
                pay_item = QtWidgets.QTableWidgetItem(payment_type)
                self.transaction_table.setItem(row_pos, 4, pay_item)

                # Tarih
                try:
                    date_text = datetime.strptime(row[5], "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M")
                except Exception:
                    date_text = row[5]
                date_item = QtWidgets.QTableWidgetItem(date_text)
                self.transaction_table.setItem(row_pos, 5, date_item)

                # Müşteri
                cust_item = QtWidgets.QTableWidgetItem(row[6] or "")
                self.transaction_table.setItem(row_pos, 6, cust_item)

                # Butonlar
                btn_widget = QtWidgets.QWidget()
                btn_layout = QtWidgets.QHBoxLayout()
                btn_layout.setContentsMargins(0, 0, 0, 0)

                # we need the full transaction tuple for callbacks; build a tuple similar to get_transactions rows but with customer_name
                tx_tuple = (row[0], row[1], row[2], row[3], row[4], row[5], row[6])

                edit_btn = QtWidgets.QPushButton("Düzenle")
                edit_btn.setFixedWidth(70)
                edit_btn.clicked.connect(lambda _, r=tx_tuple: self.edit_transaction(r))

                delete_btn = QtWidgets.QPushButton("Sil")
                delete_btn.setFixedWidth(70)
                delete_btn.clicked.connect(lambda _, r=tx_tuple: self.delete_transaction(r))

                btn_layout.addWidget(edit_btn)
                btn_layout.addWidget(delete_btn)
                btn_widget.setLayout(btn_layout)

                self.transaction_table.setCellWidget(row_pos, 7, btn_widget)
            except Exception:
                print("load_all_transactions satır işleme hatası:\n", traceback.format_exc())

        # Not: istatistikler tüm müşteriler için değil seçili müşteri için hesaplanıyor.
        # Eğer tüm müşteriler gösteriliyorsa istatistikleri temizle:
        self.total_paid_label.setText("₺ 0.00")
        self.total_debt_label.setText("₺ 0.00")
        self.monthly_paid_label.setText("₺ 0.00")
        self.monthly_debt_label.setText("₺ 0.00")

    def reload_table(self):
        filter_text = self.search.text().strip()
        rows = self.db.list_customers(filter_text if filter_text else None)
        self.table.setRowCount(0)
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, val in enumerate(r):
                display = ""
                if val is not None:
                    if col == 7:
                        try:
                            display = "{:,.2f}".format(float(val))
                        except Exception:
                            display = str(val)
                    else:
                        display = str(val)
                item = QtWidgets.QTableWidgetItem(display)
                if col == 7:
                    item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, item)
        self.total_label.setText(f"Toplam Borç: ₺ {self.db.get_total_debt():,.2f}")

    def load_transactions(self):
        selected_id = self.get_selected_id()
        if selected_id:
            self.current_customer_id = selected_id
            self.transaction_btn.setEnabled(True)
            self.setup_transactions_tab(selected_id)
        else:
            self.current_customer_id = None
            self.transaction_btn.setEnabled(False)

    def load_transactions_data(self, customer_id, filters=None):
        if not customer_id:
            self.transaction_table.setRowCount(0)
            return
        self.current_customer_id = customer_id
        transactions = self.db.get_transactions(customer_id)
        self.transaction_table.setRowCount(0)

        for row in transactions:
            try:
                if filters:
                    try:
                        trans_date = datetime.strptime(row[5], "%Y-%m-%d %H:%M:%S").date()
                    except Exception:
                        try:
                            trans_date = datetime.strptime(row[5], "%Y-%m-%d").date()
                        except Exception:
                            trans_date = None
                    if (filters.get('start_date') and trans_date and trans_date < filters['start_date']) or \
                       (filters.get('end_date') and trans_date and trans_date > filters['end_date']):
                        continue

                    if filters.get('type') == 'income' and row[3] != 'income':
                        continue
                    if filters.get('type') == 'expense' and row[3] != 'expense':
                        continue
                    if filters.get('payment') and filters['payment'] != row[4]:
                        continue

                row_pos = self.transaction_table.rowCount()
                self.transaction_table.insertRow(row_pos)

                transaction_type = "Ödeme" if row[3] == 'income' else "Borç"
                payment_type = "Nakit" if row[4] == 'cash' else "Kart"
                color = QtGui.QColor(76, 175, 80) if row[3] == 'income' else QtGui.QColor(244, 67, 54)

                # ID
                id_item = QtWidgets.QTableWidgetItem(str(row[0]))
                self.transaction_table.setItem(row_pos, 0, id_item)

                # Tutar
                amt_item = QtWidgets.QTableWidgetItem(f"₺ {abs(float(row[1])):,.2f}")
                amt_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
                amt_item.setForeground(color)
                self.transaction_table.setItem(row_pos, 1, amt_item)

                # Açıklama
                desc_item = QtWidgets.QTableWidgetItem(row[2] or "")
                self.transaction_table.setItem(row_pos, 2, desc_item)

                # Tür
                type_item = QtWidgets.QTableWidgetItem(transaction_type)
                type_item.setForeground(color)
                self.transaction_table.setItem(row_pos, 3, type_item)

                # Ödeme
                pay_item = QtWidgets.QTableWidgetItem(payment_type)
                self.transaction_table.setItem(row_pos, 4, pay_item)

                # Tarih
                try:
                    date_text = datetime.strptime(row[5], "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M")
                except Exception:
                    date_text = row[5]
                date_item = QtWidgets.QTableWidgetItem(date_text)
                self.transaction_table.setItem(row_pos, 5, date_item)

                # Müşteri adı (aldığımız sorguda yok; çekmek için DB sorgulayalım)
                cur = self.db.conn.cursor()
                cur.execute("SELECT first_name || ' ' || last_name FROM customers WHERE id=?", (customer_id,))
                name_row = cur.fetchone()
                cust_name = name_row[0] if name_row else ""
                cust_item = QtWidgets.QTableWidgetItem(cust_name)
                self.transaction_table.setItem(row_pos, 6, cust_item)

                btn_widget = QtWidgets.QWidget()
                btn_layout = QtWidgets.QHBoxLayout()
                btn_layout.setContentsMargins(0, 0, 0, 0)

                tx_tuple = (row[0], row[1], row[2], row[3], row[4], row[5])

                edit_btn = QtWidgets.QPushButton("Düzenle")
                edit_btn.setFixedWidth(70)
                edit_btn.clicked.connect(lambda _, r=tx_tuple: self.edit_transaction(r))

                delete_btn = QtWidgets.QPushButton("Sil")
                delete_btn.setFixedWidth(70)
                delete_btn.clicked.connect(lambda _, r=tx_tuple: self.delete_transaction(r))

                btn_layout.addWidget(edit_btn)
                btn_layout.addWidget(delete_btn)
                btn_widget.setLayout(btn_layout)

                self.transaction_table.setCellWidget(row_pos, 7, btn_widget)
            except Exception:
                print("load_transactions_data satır hata:\n", traceback.format_exc())

        self.update_stats(customer_id)

    def apply_filters(self):
        filters = {
            'type': None if self.filter_type.currentIndex() == 0 else
                   'income' if self.filter_type.currentIndex() == 1 else 'expense',
            'payment': None if self.filter_payment.currentIndex() == 0 else
                       'cash' if self.filter_payment.currentIndex() == 1 else 'card',
            'start_date': self.filter_start_date.date().toPyDate(),
            'end_date': self.filter_end_date.date().toPyDate()
        }
        # reload using current selected customer
        if self.current_customer_id:
            self.load_transactions_data(self.current_customer_id, filters)
        else:
            self.load_all_transactions(filters)

    def update_stats(self, customer_id):
        try:
            stats = self.db.get_transaction_stats(customer_id)
            total_paid = stats['total_paid']
            total_debt = stats['total_debt']
            difference = total_paid - total_debt
            
            self.total_paid_label.setText(f"₺ {total_paid:,.2f}")
            self.total_debt_label.setText(f"₺ {total_debt:,.2f}")
            
            # Farkı güncelle ve renklendir
            if difference >= 0:
                self.difference_label.setText(f"₺ {difference:,.2f} (Alacak)")
                self.difference_label.setStyleSheet("color: green; font-weight: bold;")
            else:
                self.difference_label.setText(f"₺ {abs(difference):,.2f} (Borç)")
                self.difference_label.setStyleSheet("color: red; font-weight: bold;")
                
            # ... (diğer istatistikler aynı)
        except Exception:
            print("update_stats hata:\n", traceback.format_exc())

    def get_selected_id(self):
        sel = self.table.selectedItems()
        if not sel:
            return None
        try:
            return int(self.table.item(sel[0].row(), 0).text())  # type: ignore
        except Exception:
            return None

    def add_customer(self):
        dlg = CustomerDialog(self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            if not data:
                return
            if not data['first_name'] or not data['last_name']:
                QtWidgets.QMessageBox.warning(self, "Eksik bilgi", "Ad ve soyad zorunludur.")
                return
            try:
                self.db.add_customer(**data)
                self.reload_table()
                self.refresh_customer_combo()
            except sqlite3.IntegrityError as e:
                QtWidgets.QMessageBox.warning(self, "Hata", "Bu TC no veya telefon numarası zaten kayıtlı!")
            except Exception:
                QtWidgets.QMessageBox.warning(self, "Hata", "Müşteri eklenirken beklenmeyen bir hata oluştu.")
                print("add_customer hata:\n", traceback.format_exc())

    def edit_customer(self):
        cid = self.get_selected_id()
        if cid is None:
            QtWidgets.QMessageBox.information(self, "Seçim yok", "Lütfen bir müşteri seçin.")
            return

        cust = None
        for r in self.db.list_customers():
            if r[0] == cid:
                cust = {
                    'first_name': r[1], 'last_name': r[2],
                    'tc_no': r[3], 'phone': r[4],
                    'address': r[5], 'notes': r[6],
                    'debt': r[7]
                }
                break

        dlg = CustomerDialog(self, customer=cust)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            if not data:
                return
            try:
                self.db.update_customer(cid, **data)
                self.reload_table()
                self.refresh_customer_combo()
            except sqlite3.IntegrityError:
                QtWidgets.QMessageBox.warning(self, "Hata", "Bu TC no veya telefon numarası zaten başka müşteride kayıtlı!")
            except Exception:
                QtWidgets.QMessageBox.warning(self, "Hata", "Müşteri güncellenirken hata oluştu.")
                print("edit_customer hata:\n", traceback.format_exc())

    def delete_customer(self):
        cid = self.get_selected_id()
        if cid is None:
            QtWidgets.QMessageBox.information(self, "Seçim yok", "Lütfen bir müşteri seçin.")
            return

        reply = QtWidgets.QMessageBox.question(
            self, "Onay", "Müşteriyi silmek istiyor musunuz?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            try:
                self.db.delete_customer(cid)
                self.reload_table()
                self.refresh_customer_combo()
            except Exception:
                QtWidgets.QMessageBox.warning(self, "Hata", "Müşteri silinirken hata oluştu.")
                print("delete_customer hata:\n", traceback.format_exc())

    def add_transaction(self):
        selected_id = self.get_selected_id()
        if not selected_id:
            QtWidgets.QMessageBox.warning(self, "Uyarı", "Lütfen bir müşteri seçin!")
            return

        dlg = TransactionDialog(self, selected_id)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            try:
                self.db.add_transaction(selected_id, data['amount'], data['description'],
                                        data['transaction_type'], data['payment_type'], date=data.get('date'))

                self.reload_table()
                # Eğer transactions tabı açık ve aynı müşteri seçili ise güncelle
                if self.current_customer_id == selected_id:
                    self.load_transactions_data(selected_id)
                else:
                    self.load_all_transactions()
                self.tabs.setCurrentIndex(1)

            except Exception:
                QtWidgets.QMessageBox.warning(self, "Hata", "Hareket eklenirken hata oluştu.")
                print("add_transaction hata:\n", traceback.format_exc())

    def edit_transaction(self, transaction_data):
        # transaction_data is a tuple (id, amount, description, transaction_type, payment_type, date, [customer_name])
        transaction = {
            'id': transaction_data[0],
            'amount': transaction_data[1],
            'description': transaction_data[2],
            'transaction_type': transaction_data[3],
            'payment_type': transaction_data[4],
            'date': transaction_data[5]
        }

        dlg = TransactionDialog(self, self.current_customer_id, transaction)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            try:
                updated = self.db.update_transaction(transaction['id'], data['amount'], data['description'],
                                                     data['transaction_type'], data['payment_type'], date=data.get('date'))
                if not updated:
                    QtWidgets.QMessageBox.warning(self, "Hata", "Hareket güncellenemedi!")
                self.reload_table()
                if self.current_customer_id:
                    self.load_transactions_data(self.current_customer_id)
                else:
                    self.load_all_transactions()
            except Exception:
                QtWidgets.QMessageBox.warning(self, "Hata", "Hareket güncellenirken hata oluştu.")
                print("edit_transaction hata:\n", traceback.format_exc())

    def delete_transaction(self, transaction_data):
        reply = QtWidgets.QMessageBox.question(
            self, "Onay", "Bu hareketi silmek istediğinize emin misiniz?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            try:
                if self.db.delete_transaction(transaction_data[0]):
                    self.reload_table()
                    if self.current_customer_id:
                        self.load_transactions_data(self.current_customer_id)
                    else:
                        self.load_all_transactions()
                else:
                    QtWidgets.QMessageBox.warning(self, "Hata", "Hareket silinirken bir hata oluştu!")
            except Exception:
                QtWidgets.QMessageBox.warning(self, "Hata", "Hata oluştu.")
                print("delete_transaction hata:\n", traceback.format_exc())

def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
