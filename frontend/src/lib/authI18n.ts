/**
 * Author: Joonyoung Ki
 *
 * Purpose: Korean/English UI strings for the account features (login,
 * registration, account menu, wishlist). Kept separate from the main
 * translation table so the two can evolve independently. Korean entries are
 * intentional: they are the ko language option.
 */

import type { Lang } from '../types'

export interface AuthTranslation {
  login: string
  register: string
  logout: string
  accountMenu: string
  savedJobs: string
  savedJobsCount: (n: number) => string
  emailLabel: string
  emailPlaceholder: string
  passwordLabel: string
  passwordHint: string
  showPassword: string
  hidePassword: string
  loginTitle: string
  loginBody: string
  registerTitle: string
  registerBody: string
  submitLogin: string
  submitRegister: string
  submitting: string
  switchToRegister: string
  switchToLogin: string
  close: string
  errEmail: string
  errPasswordShort: string
  errPasswordWeak: string
  errCredentials: string
  errEmailTaken: string
  errRateLimit: string
  errNotConfigured: string
  errNetwork: string
  errGeneric: string
  save: string
  unsave: string
  saveNeedsLogin: string
  savedToast: string
  removedToast: string
  saveFailed: string
  wishlistTitle: string
  wishlistSub: string
  wishlistEmptyTitle: string
  wishlistEmptyBody: string
  wishlistErrorTitle: string
  wishlistRetry: string
  wishlistRemove: string
  noSummary: string
  salaryUnknown: string
}

export const authTranslations: Record<Lang, AuthTranslation> = {
  ko: {
    login: '로그인',
    register: '회원가입',
    logout: '로그아웃',
    accountMenu: '계정 메뉴',
    savedJobs: '저장한 공고',
    savedJobsCount: (n) => `${n}건`,
    emailLabel: '이메일',
    emailPlaceholder: 'name@example.com',
    passwordLabel: '비밀번호',
    passwordHint: '8자 이상, 영문과 숫자를 모두 포함해야 합니다.',
    showPassword: '비밀번호 표시',
    hidePassword: '비밀번호 숨기기',
    loginTitle: '다시 오신 것을 환영합니다',
    loginBody: '로그인하면 마음에 드는 공고를 저장하고 나중에 다시 볼 수 있습니다.',
    registerTitle: '계정 만들기',
    registerBody: '이메일로 가입하면 관심 공고를 저장할 수 있습니다. 로그인 없이도 분석은 계속 사용할 수 있어요.',
    submitLogin: '로그인',
    submitRegister: '가입하기',
    submitting: '처리 중…',
    switchToRegister: '계정이 없으신가요? 회원가입',
    switchToLogin: '이미 계정이 있으신가요? 로그인',
    close: '닫기',
    errEmail: '올바른 이메일 주소를 입력해주세요.',
    errPasswordShort: '비밀번호는 8자 이상이어야 합니다.',
    errPasswordWeak: '비밀번호에 영문과 숫자를 모두 포함해주세요.',
    errCredentials: '이메일 또는 비밀번호가 올바르지 않습니다.',
    errEmailTaken: '이미 가입된 이메일입니다.',
    errRateLimit: '시도 횟수가 너무 많습니다. 잠시 후 다시 시도해주세요.',
    errNotConfigured: '서버에 로그인 기능이 아직 설정되지 않았습니다.',
    errNetwork: '서버에 연결할 수 없습니다.',
    errGeneric: '요청을 처리하지 못했습니다. 다시 시도해주세요.',
    save: '공고 저장',
    unsave: '저장 해제',
    saveNeedsLogin: '로그인하면 공고를 저장할 수 있습니다.',
    savedToast: '저장한 공고에 추가했습니다.',
    removedToast: '저장한 공고에서 제거했습니다.',
    saveFailed: '저장 상태를 바꾸지 못했습니다. 다시 시도해주세요.',
    wishlistTitle: '저장한 공고',
    wishlistSub: '하트를 눌러 저장한 공고를 모아봅니다.',
    wishlistEmptyTitle: '저장한 공고가 없습니다',
    wishlistEmptyBody: '매칭 결과 카드의 하트를 눌러 관심 공고를 저장해 보세요.',
    wishlistErrorTitle: '저장 목록을 불러오지 못했습니다',
    wishlistRetry: '다시 시도',
    wishlistRemove: '저장 해제',
    noSummary: '요약 정보가 없습니다.',
    salaryUnknown: '연봉 정보 없음',
  },
  en: {
    login: 'Log in',
    register: 'Sign up',
    logout: 'Log out',
    accountMenu: 'Account menu',
    savedJobs: 'Saved jobs',
    savedJobsCount: (n) => `${n}`,
    emailLabel: 'Email',
    emailPlaceholder: 'name@example.com',
    passwordLabel: 'Password',
    passwordHint: 'At least 8 characters, with both letters and digits.',
    showPassword: 'Show password',
    hidePassword: 'Hide password',
    loginTitle: 'Welcome back',
    loginBody: 'Log in to save the jobs you like and revisit them later.',
    registerTitle: 'Create your account',
    registerBody: 'Sign up with your email to save jobs. You can still run the analysis without an account.',
    submitLogin: 'Log in',
    submitRegister: 'Create account',
    submitting: 'Working…',
    switchToRegister: "Don't have an account? Sign up",
    switchToLogin: 'Already have an account? Log in',
    close: 'Close',
    errEmail: 'Please enter a valid email address.',
    errPasswordShort: 'Password must be at least 8 characters.',
    errPasswordWeak: 'Password must include both letters and digits.',
    errCredentials: 'Incorrect email or password.',
    errEmailTaken: 'This email is already registered.',
    errRateLimit: 'Too many attempts. Please try again later.',
    errNotConfigured: 'Login is not configured on the server yet.',
    errNetwork: 'Cannot reach the server.',
    errGeneric: 'The request could not be processed. Please try again.',
    save: 'Save job',
    unsave: 'Remove from saved',
    saveNeedsLogin: 'Log in to save jobs.',
    savedToast: 'Added to your saved jobs.',
    removedToast: 'Removed from your saved jobs.',
    saveFailed: 'Could not update the saved state. Please try again.',
    wishlistTitle: 'Saved jobs',
    wishlistSub: 'Jobs you saved with the heart button.',
    wishlistEmptyTitle: 'No saved jobs yet',
    wishlistEmptyBody: 'Tap the heart on a match card to save a job you like.',
    wishlistErrorTitle: 'Could not load your saved jobs',
    wishlistRetry: 'Try again',
    wishlistRemove: 'Remove',
    noSummary: 'No summary available.',
    salaryUnknown: 'Salary not listed',
  },
}
