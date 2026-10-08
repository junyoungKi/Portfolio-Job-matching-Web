import type { Lang } from '../types'

export interface Translation {
  title: string
  subtitle: string
  statsLabel: string
  keywordLabel: string
  keywordPlaceholder: string
  locationLabel: string
  locAll: string
  resumeLabel: string
  dropHint: string
  dropActive: string
  chooseFile: string
  changeFile: string
  removeFile: string
  pdfOnly: string
  btnStart: string
  analyzing: string
  filterTitle: string
  labelExp: string
  labelType: string
  labelSkills: string
  expLevels: Record<string, string>
  typeLevels: Record<string, string>
  applyFilters: string
  resetFilters: string
  resultTitle: string
  resultCount: (n: number) => string
  matchLabel: string
  showDetail: string
  hideDetail: string
  detailTitle: string
  matchedSkills: string
  noSummary: string
  emptyIdleTitle: string
  emptyIdleBody: string
  emptyResultTitle: string
  emptyResultBody: string
  errFill: string
  errNetwork: string
  errServer: string
  errNotFound: string
  errPdf: string
  retry: string
  language: string
}

export const translations: Record<Lang, Translation> = {
  ko: {
    title: '스마트 잡 AI',
    subtitle: '북미 커리어 매칭 대시보드',
    statsLabel: '데이터베이스 공고 수',
    keywordLabel: '희망 직무',
    keywordPlaceholder: '예: C++ 개발자',
    locationLabel: '희망 지역',
    locAll: '북미 전체',
    resumeLabel: '이력서 업로드 (PDF)',
    dropHint: 'PDF 파일을 여기에 끌어다 놓거나 클릭해서 선택하세요',
    dropActive: '여기에 놓으세요',
    chooseFile: '파일 선택',
    changeFile: '다른 파일 선택',
    removeFile: '파일 제거',
    pdfOnly: 'PDF 파일만 업로드할 수 있습니다.',
    btnStart: 'AI 분석 시작',
    analyzing: 'AI가 이력서를 분석하는 중입니다…',
    filterTitle: '고급 필터',
    labelExp: '경력 수준',
    labelType: '고용 형태',
    labelSkills: '주요 기술 (가중치 적용)',
    expLevels: { Entry: '신입 (Entry)', Junior: '주니어', Mid: '미들/시니어' },
    typeLevels: { 'Full-time': '정규직', Internship: '인턴십', Contract: '계약직' },
    applyFilters: '필터 다시 적용',
    resetFilters: '초기화',
    resultTitle: 'AI 추천 매칭 결과',
    resultCount: (n) => `${n}건`,
    matchLabel: '매칭률',
    showDetail: '상세 분석 보기',
    hideDetail: '상세 분석 닫기',
    detailTitle: '상세 분석',
    matchedSkills: '일치 스킬',
    noSummary: '요약 정보가 없습니다.',
    emptyIdleTitle: '아직 분석 결과가 없습니다',
    emptyIdleBody: '이력서(PDF)와 희망 직무를 입력하고 AI 분석을 시작해 보세요.',
    emptyResultTitle: '조건에 맞는 결과가 없습니다',
    emptyResultBody: '필터를 완화하거나 지역을 바꿔 다시 시도해 보세요.',
    errFill: 'PDF 이력서와 희망 직무를 모두 입력해주세요.',
    errNetwork: '서버에 연결할 수 없습니다. 백엔드가 실행 중인지 확인해주세요.',
    errServer: '요청을 처리하지 못했습니다.',
    errNotFound: '이력서를 찾을 수 없습니다. 다시 업로드해주세요.',
    errPdf: 'PDF 파일만 업로드할 수 있습니다.',
    retry: '다시 시도',
    language: '언어',
  },
  en: {
    title: 'Smart Job AI',
    subtitle: 'North America Career Matching Dashboard',
    statsLabel: 'Jobs in database',
    keywordLabel: 'Target role',
    keywordPlaceholder: 'e.g. C++ Developer',
    locationLabel: 'Location',
    locAll: 'All North America',
    resumeLabel: 'Resume (PDF)',
    dropHint: 'Drag & drop your PDF here, or click to browse',
    dropActive: 'Drop it here',
    chooseFile: 'Choose file',
    changeFile: 'Choose another file',
    removeFile: 'Remove file',
    pdfOnly: 'Only PDF files are supported.',
    btnStart: 'Start AI analysis',
    analyzing: 'AI is analysing your resume…',
    filterTitle: 'Advanced filters',
    labelExp: 'Experience level',
    labelType: 'Employment type',
    labelSkills: 'Key skills (weighted)',
    expLevels: { Entry: 'Entry level', Junior: 'Junior', Mid: 'Mid/Senior' },
    typeLevels: { 'Full-time': 'Full-time', Internship: 'Internship', Contract: 'Contract' },
    applyFilters: 'Re-apply filters',
    resetFilters: 'Reset',
    resultTitle: 'AI recommended matches',
    resultCount: (n) => `${n} result${n === 1 ? '' : 's'}`,
    matchLabel: 'Match',
    showDetail: 'Show detailed analysis',
    hideDetail: 'Hide detailed analysis',
    detailTitle: 'Detailed analysis',
    matchedSkills: 'Matched skills',
    noSummary: 'No summary available.',
    emptyIdleTitle: 'No results yet',
    emptyIdleBody: 'Upload your resume (PDF), enter a target role and start the AI analysis.',
    emptyResultTitle: 'No matching results found',
    emptyResultBody: 'Try relaxing the filters or choosing a different location.',
    errFill: 'Please provide a PDF resume and a target role.',
    errNetwork: 'Cannot reach the server. Make sure the backend is running.',
    errServer: 'The request could not be processed.',
    errNotFound: 'Resume not found. Please upload it again.',
    errPdf: 'Only PDF files are supported.',
    retry: 'Try again',
    language: 'Language',
  },
}
