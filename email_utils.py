"""
email_utils.py — Email sending and OTP management utilities.
"""
import os
import random
import string
from datetime import datetime, timedelta
from flask_mail import Mail, Message
import db

mail = Mail()


def send_email(subject, recipients, html_body):
    """Send an email with HTML content."""
    try:
        msg = Message(
            subject=subject,
            recipients=recipients if isinstance(recipients, list) else [recipients],
            html=html_body
        )
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


def generate_otp(length=6):
    """Generate a random numeric OTP."""
    return ''.join(random.choices(string.digits, k=length))


def create_password_reset_otp(user_id, otp_length=6):
    """Create a password reset OTP for a user (valid for 15 minutes)."""
    otp = generate_otp(otp_length)
    expires_at = datetime.utcnow() + timedelta(minutes=15)

    try:
        # Invalidate any existing unused OTPs for this user
        db.execute(
            "UPDATE password_reset_otps SET is_used=1 WHERE user_id=? AND is_used=0",
            [user_id]
        )

        # Create new OTP
        db.execute(
            "INSERT INTO password_reset_otps (user_id, otp, expires_at) VALUES (?,?,?)",
            [user_id, otp, expires_at]
        )
        return otp
    except Exception as e:
        print(f"Failed to create OTP: {e}")
        return None


def verify_password_reset_otp(user_id, otp):
    """Verify a password reset OTP."""
    try:
        result = db.query_one(
            """SELECT id FROM password_reset_otps
               WHERE user_id=? AND otp=? AND is_used=0 AND expires_at > NOW()""",
            [user_id, otp]
        )

        if result:
            # Mark OTP as used
            db.execute(
                "UPDATE password_reset_otps SET is_used=1 WHERE id=?",
                [result['id']]
            )
            return True
        return False
    except Exception as e:
        print(f"Failed to verify OTP: {e}")
        return False


def send_password_reset_email(email, first_name, otp):
    """Send password reset email with OTP."""
    html_body = f"""
    <html>
    <body style="font-family: 'Lato', sans-serif; color: #2A1F0E;">
        <div style="max-width: 500px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #1A6B72; margin-bottom: 20px;">Reset Your Password</h2>

            <p>Hi {first_name},</p>

            <p>We received a request to reset your Talbeena account password. Use the OTP below to reset it:</p>

            <div style="background: #F5E6C8; padding: 20px; border-radius: 8px; text-align: center; margin: 30px 0;">
                <p style="font-size: 32px; font-weight: bold; color: #C8922A; letter-spacing: 4px; margin: 0;">
                    {otp}
                </p>
            </div>

            <p><strong>This OTP expires in 15 minutes.</strong></p>

            <p>If you didn't request a password reset, please ignore this email or contact support.</p>

            <hr style="border: none; border-top: 1px solid #E8D9BC; margin: 30px 0;">

            <p style="color: #8A7455; font-size: 12px;">
                Talbeena | htwoindia@gmail.com
            </p>
        </div>
    </body>
    </html>
    """

    return send_email("Reset Your Talbeena Password", [email], html_body)


def send_welcome_email(email, first_name):
    """Send welcome email to new users."""
    html_body = f"""
    <html>
    <body style="font-family: 'Lato', sans-serif; color: #2A1F0E;">
        <div style="max-width: 500px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #1A6B72; margin-bottom: 20px;">Welcome to Talbeena!</h2>

            <p>Hi {first_name},</p>

            <p>Thank you for creating an account with us. We're excited to have you as part of the Talbeena family!</p>

            <p>With your Talbeena account, you can:</p>
            <ul style="color: #5C4A2A;">
                <li>Track your orders in real-time</li>
                <li>Save your addresses for faster checkout</li>
                <li>View your order history</li>
                <li>Receive exclusive offers</li>
            </ul>

            <p style="margin-top: 30px;">
                <a href="https://talbeena.com" style="background: #1A6B72; color: white; padding: 10px 30px; border-radius: 6px; text-decoration: none; display: inline-block;">
                    Start Shopping
                </a>
            </p>

            <hr style="border: none; border-top: 1px solid #E8D9BC; margin: 30px 0;">

            <p style="color: #8A7455; font-size: 12px;">
                Talbeena | htwoindia@gmail.com
            </p>
        </div>
    </body>
    </html>
    """

    return send_email("Welcome to Talbeena!", [email], html_body)
