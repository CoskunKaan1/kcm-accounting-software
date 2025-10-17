Customer and Accounting Tracking Application
This project is a desktop customer relationship management (CRM) and basic accounting tracking application developed using PyQt6 and SQLite. It is designed to easily manage customer information, debit-credit statuses, and account transactions, especially for insurance agencies, freelancers, or small businesses.

Screenshots
Here are some screenshots showcasing the application's interface and functionality.

Customers Tab: This view displays all registered customers, their contact details, and current balance.




Transactions Tab: This tab allows you to view, filter, and export all financial transactions, along with customer-specific statistics.




✨ Features
Customer Management
Add, Delete, and Update Customers: Easily manage your customer portfolio.

Detailed Customer Information: Store information such as Name, Surname, TR ID No, Phone, Address, and special notes for each customer.

Dynamic Search: Instantly search by name, phone, or TR ID number in the Customers tab.

Total Balance Display: View the total debit balance of all customers instantly in the status bar at the bottom of the main screen.

Account Transactions
Debit and Payment Operations: Add debts (expenses) to your customers or receive payments (income) from them.

Transaction Details: Record details such as amount, description, transaction date, and payment type (Cash/Card) for each transaction.

Automatic Balance Update: Each transaction automatically updates the debit balance of the relevant customer.

View All Transactions: See all account transactions for a specific customer or all customers in a single list on the "Transactions" tab.

Filtering and Reporting
Advanced Filtering: Filter account transactions by transaction type (Payment/Debit), payment method (Cash/Card), and a specific date range.

Customer-Based Statistics: View instant statistics for a selected customer, such as total payments, total debits, and net balance (credit/debit status).

Export to PDF: Export a complete account statement for a selected customer, including summary statistics, as a sleek PDF file.

Technical Aspects
Local Database: All data is stored in a local SQLite database file named customers.db, requiring no additional server setup.

Modern Interface: The application is designed with a modern and dark theme.

🛠️ Technologies Used
Python 3

PyQt6: For the desktop application interface.

SQLite 3: For database management.
