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
    first_name = serializers.CharField(required=True, max_length=150, label='이름')

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'password',
            'password_confirm',
            'first_name',
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

        temp_user = User(username=attrs.get('username'), email=attrs.get('email'), first_name=attrs.get('first_name'))
        try:
            validate_password(password, user=temp_user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': list(exc.messages)})

        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')

        try:
            user = User.objects.create_user(**validated_data)
        except IntegrityError:
            raise serializers.ValidationError({'email': '이미 사용 중인 이메일입니다.'})
        return user


class ProfileSerializer(serializers.ModelSerializer):
    """본인 프로필 조회 전용 시리얼라이저 (전 필드 read-only)."""

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'phone_number', 'balance', 'created_at']
        read_only_fields = fields


class PasswordChangeSerializer(serializers.Serializer):
    """비밀번호 변경 요청을 처리하는 시리얼라이저."""

    current_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True, max_length=128)
    new_password_confirm = serializers.CharField(write_only=True, required=True, max_length=128)

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('현재 비밀번호가 일치하지 않습니다.')
        return value

    def validate(self, attrs):
        new_password = attrs.get('new_password')
        new_password_confirm = attrs.get('new_password_confirm')
        current_password = attrs.get('current_password')

        if new_password != new_password_confirm:
            raise serializers.ValidationError({'new_password_confirm': '비밀번호가 일치하지 않습니다.'})

        if new_password == current_password:
            raise serializers.ValidationError({'new_password': '현재 비밀번호와 동일한 비밀번호로는 변경할 수 없습니다.'})

        user = self.context['request'].user
        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'new_password': list(exc.messages)})

        return attrs

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user
