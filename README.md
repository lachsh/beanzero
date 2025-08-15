# Bean0

## Guiding principles

- Zero-based budgeting philosophy, following in the footsteps of YNAB/ActualBudget
- Terminal-based UI is simple, attractive, and efficient
- Beancount ledger is a _read-only_ source of transaction data - we do not modify any beancount files at all
- Budget accounts, categories, options, etc. are stored in a config file - UI editing of these things is out of scope
- The actual money assigned to categories + any other budget-specific data is stored in a JSON data file, and these things _are_ intended to be edited primarily with the UI
- Budgeting is a subset of overall financial tracking, and so the budget can be configured to operate over any subset of relevant beancount accounts
- The underlying maths is predictable - there's no magic around "present" or "future" months, and a month's balances depend only on data from that and all previous months

## Budget structure

We use the unqualified terms account, transaction, and posting in the beancount sense.

The highest level of structure is the **budget**, which will likely map one-to-one to a beancount ledger.

Within a budget, there are **budget accounts**. These are an identified subset of beancount accounts that contain the money for all tracked budgeting and spending. They will likely comprise:

- All asset accounts containing liquid cash
- All liability accounts for credit cards and other cash advance-type loans

Any asset or liability beancount account that is not a budget account is an **off-budget account**.

Budgeting is done by **assigning** the money in budget accounts to **categories** of spending, like rent, utilities, groceries, etc. A **category balance** is increased by assigning money, and decreased by spending. Each category can have any number of beancount accounts assigned, and postings to these accounts are categorised as spending from the corresponding category. As such, the accounts used in categories will likely comprise:

- All day-to-day/month-to-month expense accounts
- Off-budget asset and liability accounts for investing or paying down debt

The net amount of unspent money in all budget accounts that has not been assigned to a category is known as the **to be assigned** balance. In zero-based budgeting, the intent is to keep this value at zero. The invariant that governs zero-based budgeting, analogous to beancount's "all postings in a transaction sum to zero", is "the to-be-assigned + all category balances equal the sum of cash in all on-budget accounts".

## Mapping from beancount

The following process is used to extract budget activity from a beancount ledger:

- For each beancount transaction, the net **flow** into/out of all of the budget accounts is calculated. If this is zero, no money is entering or leaving the budget, so the transaction is not relevant and is skipped.
- Postings to accounts corresponding to categories are summed, and this is tracked as per-category **spending**. The signs are flipped to represent money leaving the budget, so a `100 AUD` posting to an `Expenses:...` is counted as `-100 AUD` spending in the corresponding category.
- The net result of flow and spending is thus **funding**, which, when positive, represents money entering the budget as ready to assign, without being associated with a specific category.

This gives maximal flexibility for structuring budget categories and accounts, reflecting the flexibility of beancount transactions and postings. That said, the vast majority of transactions fall into one of the following options:

- Transfer between off-budget accounts: flow is zero, skipped
- Transfer between on-budget accounts: flow is zero, skipped
- Transfer out of an on-budget account, to an expense account or off-budget account: flow = spending = negative amount transferred, funding = zero
- Transfer into an on-budget account, from an income account or off-budget account: flow = funding = positive amount transferred, spending = zero

It's possible for spending to be positive, and that is fine. This is usually the case when refunds or reimbursements cause a negative posting to an expenses account.

While it is similarly possible for funding to be negative, this should be avoided. That is a sign that money is leaving the budget without being tracked by a category, and so the shortfall will have to be made up by reducing already assigned amounts. If this is happening, it's better to instead add the receiving account to an existing or new budget category to accurately reflect the expense, so it can be properly budgeted for in future.
