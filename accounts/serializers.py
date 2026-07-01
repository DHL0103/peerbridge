from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import serializers

from accounts.models import User


class RegisterSerializer(serializers.ModelSerializer):
    """회원가입 요청을 처리하는 시리얼라이저.

    password/password_confirm은 입력에만 사용되며 응답에는 노출되지 않는다.
    """

    password = serializers.CharField(write_only=True, max_length=128)
    password_confirm = serializers.CharField(write_only=True, max_length=128)
    email = serializers.EmailField(required=True)

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'password',
            'password_confirm',
            'phone_number',
            'balance',
            'created_at',
        ]
        read_only_fields = ['id', 'balance', 'created_at']

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('이미 사용 중인 이메일입니다.')
        return value

    def validate(self, attrs):
        password = attrs.get('password')
        password_confirm = attrs.get('password_confirm')

        if password != password_confirm:
            raise serializers.ValidationError({'password_confirm': '비밀번호가 일치하지 않습니다.'})

        temp_user = User(username=attrs.get('username'), email=attrs.get('email'))
        try:
            validate_password(password, user=temp_user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': list(exc.messages)})

        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')

        try:
            user = User.objects.create_user(password=password, **validated_data)
        except IntegrityError:
            raise serializers.ValidationError({'email': '이미 사용 중인 이메일입니다.'})
        return user
