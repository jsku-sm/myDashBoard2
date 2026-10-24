"""Run locally only for a NEW vault. Never replace an existing key."""
from cryptography.fernet import Fernet

if __name__ == '__main__':
    print('새 학생 자료함의 첫 설정에만 사용하세요. 기존 자료함 키와 수행평가 키를 변경하지 마세요.')
    print('[student_archive]')
    print('encryption_key = "' + Fernet.generate_key().decode('ascii') + '"')
    print('# 위 값을 Streamlit Secrets와 안전한 비밀번호 보관함에만 저장하세요. GitHub에 올리지 마세요.')
