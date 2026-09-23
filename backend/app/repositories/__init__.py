"""Data access. Repositories wrap SQLAlchemy queries; they never commit.

The service layer owns the unit of work (one session per request) and decides
when to commit, so several repository calls can form one transaction.
"""
