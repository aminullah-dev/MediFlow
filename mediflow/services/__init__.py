"""Application services — orchestrate repositories, enforce business rules.

Services own transactions (via ``Database.unit_of_work``) and permission checks.
The UI talks only to services, never to repositories or the ORM directly.
"""
