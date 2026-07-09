from dotenv import load_dotenv

from financeDatabase import BankDB, FinanceDB, RequestsDB, TransactionsDB


def main():
    load_dotenv("a.env")
    FinanceDB()
    BankDB()
    RequestsDB()
    TransactionsDB()
    print("MySQL tables initialized successfully.")


if __name__ == "__main__":
    main()
