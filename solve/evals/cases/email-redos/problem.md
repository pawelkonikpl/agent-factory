The signup endpoint sometimes hangs for minutes and pins a CPU core. It started
after the new email validation in `solve/evals/cases/email-redos/validator.py`
went live. Make validation fast again without changing which addresses it
accepts or rejects.
