"""Node adapter for the same institutional registry contract as the portal.

The node installer must bundle the standalone contract as profile_contract.py;
there is no dependency on the FastAPI application in an installed runner.
"""
if __package__ == 'infra.applications.profiles':
    from app.schemas.application_profiles import ProfileRegistry as Contract, ProfileError
else:
    from .profile_contract import ProfileRegistry as Contract, ProfileError

from ..job.protocol import JobError


class ProfileRegistry(Contract):
    def __init__(self, entries):
        try:
            super().__init__(entries)
        except ProfileError:
            raise JobError('PROFILE_UNAVAILABLE') from None

    def require(self, reference, **context):
        try:
            return super().require(reference, **context)
        except ProfileError:
            raise JobError('PROFILE_UNAVAILABLE') from None
