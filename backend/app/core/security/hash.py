#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-11
# @description: hash utility using bcrypt

import bcrypt

def bcrypt_hash(password: str) -> str:
    # Convert to byte string
    password_bytes = password.encode('utf-8')
    # Generate random salt values ​​(cost=12 is a commonly used value; the larger the value, the slower the process).
    salt = bcrypt.gensalt(rounds=12)
    # Calculate the bcrypt hash (automatically includes salt).
    hashed = bcrypt.hashpw(password_bytes, salt)
    # Convert to a string and return (commonly used when storing in a database).
    return hashed.decode('utf-8')

def verify_bcrypt(password: str, hashed_password: str) -> bool:
    # Verify password match
    password_bytes = password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)

if __name__ == "__main__":
    # Test: The same password produces different outputs (because the salt value is random).
    hash1 = bcrypt_hash("123456")
    hash2 = bcrypt_hash("123456")
    print(hash1) 
    print(hash2)  # Unlike hash1
    print(verify_bcrypt("123456", hash1))  # True (Password Match)
    print(verify_bcrypt("654321", hash1))  # False (Password does not match)