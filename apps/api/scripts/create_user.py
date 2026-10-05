"""Create a clinic and a user from the command line.

The password comes from CREATE_USER_PASSWORD or a prompt, never from an argument,
so it does not land in the shell history.

    uv run python scripts/create_user.py --clinic "Synthetic Clinic" \
        --email a@x.test --name "Synthetic Person" --roles clinician,receptionist
"""

import argparse
import getpass
import os
import sys

from sqlalchemy.orm import Session

from dentacircle.core.database import get_engine
from dentacircle.domain.roles import ROLES
from dentacircle.services.provisioning_service import (
    DuplicateEmailError,
    UnknownRoleError,
    create_user,
    get_or_create_clinic,
)


def main() -> None:
    args = _arguments()
    password = os.environ.get("CREATE_USER_PASSWORD") or getpass.getpass("Password: ")
    if not password:
        sys.exit("A password is required.")
    roles = [role.strip() for role in args.roles.split(",") if role.strip()]
    with Session(get_engine()) as session:
        clinic = get_or_create_clinic(session, args.clinic)
        try:
            user = create_user(session, clinic.id, args.email, args.name, password, roles)
        except UnknownRoleError:
            sys.exit(f"Unknown role. Choose from: {', '.join(ROLES)}")
        except DuplicateEmailError:
            sys.exit("A user with that email already exists.")
        email = user.email
        session.commit()
    print(f"Created {email} in {args.clinic} with roles: {', '.join(roles)}")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a clinic and a user.")
    parser.add_argument("--clinic", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--roles", required=True, help="Comma-separated role names.")
    return parser.parse_args()


if __name__ == "__main__":
    main()
