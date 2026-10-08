import type { Lang } from '../types'

export interface Translation {
  brand: string
  brandTag: string
  navJobs: string
  navJobsShort: string
  language: string
  themeLabel: string
  themeSystem: string
  themeLight: string
  themeDark: string
  openFilters: string
  closeFilters: string

  heroEyebrow: string
  heroTitle: string
  heroBody: string
  heroPoints: string[]
  heroPreviewLabel: string
  heroPreviewRole: string

  stepsLabel: string
  stepUpload: string
  stepConditions: string
  stepResults: string
  stepDone: string
  stepCurrent: string
  stepUpcoming: string
  stepUploadHint: string
  stepConditionsHint: string
  stepResultsHint: string

  keywordLabel: string
  keywordPlaceholder: string
  locationLabel: string
  locAll: string
  resumeLabel: string
  dropHint: string
  dropSub: string
  dropActive: string
  chooseFile: string
  changeFile: string
  removeFile: string
  btnStart: string
  btnRestart: string
  analyzing: string

  filterTitle: string
  filterSub: string
  labelExp: string
  labelType: string
  labelSkills: string
  expLevels: Record<string, string>
  typeLevels: Record<string, string>
  applyFilters: string
  applyHint: string
  resetFilters: string
  activeFilters: (n: number) => string

  statTotal: string
  statMatched: string
  statAvg: string
  statBest: string
  statTotalHint: string
  statMatchedHint: string
  statAvgHint: string
  statBestHint: string

  resultTitle: string
  resultCount: (n: number) => string
  sortLabel: string
  sortScore: string
  sortSalary: string
  sortSalaryDisabled: string
  matchLabel: string
  scoreAria: (pct: number) => string
  showDetail: string
  hideDetail: string
  detailTitle: string
  skillsTitle: string
  skillHit: string
  noSkills: string
  noSummary: string
  salaryUnknown: string
  rank: (n: number) => string

  emptyIdleTitle: string
  emptyIdleBody: string
  emptyResultTitle: string
  emptyResultBody: string
  errorTitle: string
  errFill: string
  errNetwork: string
  errServer: string
  errNotFound: string
  errPdf: string
  retry: string
  footer: string
}

export const translations: Record<Lang, Translation> = {
  ko: {
    brand: '스마트 잡 AI',
    brandTag: 'Career Match',
    navJobs: '분석 대상 공고',
    navJobsShort: '공고',
    language: '언어',
    themeLabel: '테마',
    themeSystem: '시스템 설정',
    themeLight: '라이트',
    themeDark: '다크',
    openFilters: '필터 열기',
    closeFilters: '필터 닫기',

    heroEyebrow: 'AI 커리어 매칭',
    heroTitle: '이력서 한 장으로, 나에게 맞는 북미 포지션을 찾아드립니다',
    heroBody:
      'PDF 이력서를 업로드하면 AI가 경력과 기술 스택을 분석해 수집된 채용 공고와 매칭하고, 점수와 근거를 함께 보여드립니다.',
    heroPoints: ['이력서 PDF 분석', '공고별 매칭 점수', '일치 스킬 한눈에 확인'],
    heroPreviewLabel: '미리보기 예시',
    heroPreviewRole: '백엔드 개발자',

    stepsLabel: '진행 단계',
    stepUpload: '업로드',
    stepConditions: '조건 입력',
    stepResults: '결과',
    stepDone: '완료',
    stepCurrent: '진행 중',
    stepUpcoming: '대기',
    stepUploadHint: 'PDF 이력서를 올려주세요',
    stepConditionsHint: '희망 직무와 지역을 입력하세요',
    stepResultsHint: 'AI 분석을 시작하세요',

    keywordLabel: '희망 직무',
    keywordPlaceholder: '예: C++ 개발자',
    locationLabel: '희망 지역',
    locAll: '북미 전체',
    resumeLabel: '이력서 (PDF)',
    dropHint: 'PDF 파일을 끌어다 놓거나 클릭해서 선택하세요',
    dropSub: 'PDF 형식만 지원합니다',
    dropActive: '여기에 놓으세요',
    chooseFile: '파일 선택',
    changeFile: '다른 파일 선택',
    removeFile: '파일 제거',
    btnStart: 'AI 분석 시작',
    btnRestart: '다시 분석하기',
    analyzing: 'AI가 이력서를 분석하는 중입니다…',

    filterTitle: '필터',
    filterSub: '조건을 조정해 결과를 좁혀보세요',
    labelExp: '경력 수준',
    labelType: '고용 형태',
    labelSkills: '주요 기술 (가중치 적용)',
    expLevels: { Entry: '신입 (Entry)', Junior: '주니어', Mid: '미들/시니어' },
    typeLevels: { 'Full-time': '정규직', Internship: '인턴십', Contract: '계약직' },
    applyFilters: '필터 적용',
    applyHint: '분석을 시작하면 선택한 필터가 함께 적용됩니다.',
    resetFilters: '초기화',
    activeFilters: (n) => `${n}개 선택됨`,

    statTotal: '전체 공고',
    statMatched: '매칭된 공고',
    statAvg: '평균 매칭 점수',
    statBest: '최고 매칭 점수',
    statTotalHint: '데이터베이스 기준',
    statMatchedHint: '현재 필터 기준',
    statAvgHint: '매칭 결과 평균',
    statBestHint: '가장 높은 점수',

    resultTitle: 'AI 추천 매칭 결과',
    resultCount: (n) => `${n}건`,
    sortLabel: '정렬',
    sortScore: '매칭 점수순',
    sortSalary: '연봉순',
    sortSalaryDisabled: '연봉순 (정보 없음)',
    matchLabel: '매칭률',
    scoreAria: (pct) => `매칭률 ${pct}%`,
    showDetail: '상세 분석 보기',
    hideDetail: '상세 분석 닫기',
    detailTitle: '상세 분석',
    skillsTitle: '요구 스킬',
    skillHit: '선택한 기술과 일치',
    noSkills: '등록된 스킬 정보가 없습니다.',
    noSummary: '요약 정보가 없습니다.',
    salaryUnknown: '연봉 정보 없음',
    rank: (n) => `${n}위`,

    emptyIdleTitle: '아직 분석 결과가 없습니다',
    emptyIdleBody: '이력서(PDF)와 희망 직무를 입력하고 AI 분석을 시작해 보세요.',
    emptyResultTitle: '조건에 맞는 결과가 없습니다',
    emptyResultBody: '필터를 완화하거나 지역을 바꿔 다시 시도해 보세요.',
    errorTitle: '결과를 불러오지 못했습니다',
    errFill: 'PDF 이력서와 희망 직무를 모두 입력해주세요.',
    errNetwork: '서버에 연결할 수 없습니다. 백엔드가 실행 중인지 확인해주세요.',
    errServer: '요청을 처리하지 못했습니다.',
    errNotFound: '이력서를 찾을 수 없습니다. 다시 업로드해주세요.',
    errPdf: 'PDF 파일만 업로드할 수 있습니다.',
    retry: '다시 시도',
    footer: '매칭 결과는 AI 추정이며 참고용입니다.',
  },
  en: {
    brand: 'Smart Job AI',
    brandTag: 'Career Match',
    navJobs: 'Jobs analysed',
    navJobsShort: 'Jobs',
    language: 'Language',
    themeLabel: 'Theme',
    themeSystem: 'System',
    themeLight: 'Light',
    themeDark: 'Dark',
    openFilters: 'Open filters',
    closeFilters: 'Close filters',

    heroEyebrow: 'AI career matching',
    heroTitle: 'One resume. The right North American roles, found by AI.',
    heroBody:
      'Upload your PDF resume and our AI analyses your experience and stack, matches it against collected job postings, and shows the score and reasoning behind every match.',
    heroPoints: ['PDF resume analysis', 'Per-job match score', 'Matched skills at a glance'],
    heroPreviewLabel: 'Sample preview',
    heroPreviewRole: 'Backend Engineer',

    stepsLabel: 'Progress',
    stepUpload: 'Upload',
    stepConditions: 'Preferences',
    stepResults: 'Results',
    stepDone: 'Done',
    stepCurrent: 'In progress',
    stepUpcoming: 'Upcoming',
    stepUploadHint: 'Add your PDF resume',
    stepConditionsHint: 'Enter a target role and location',
    stepResultsHint: 'Start the AI analysis',

    keywordLabel: 'Target role',
    keywordPlaceholder: 'e.g. C++ Developer',
    locationLabel: 'Location',
    locAll: 'All North America',
    resumeLabel: 'Resume (PDF)',
    dropHint: 'Drag & drop your PDF here, or click to browse',
    dropSub: 'PDF files only',
    dropActive: 'Drop it here',
    chooseFile: 'Choose file',
    changeFile: 'Choose another file',
    removeFile: 'Remove file',
    btnStart: 'Start AI analysis',
    btnRestart: 'Analyse again',
    analyzing: 'AI is analysing your resume…',

    filterTitle: 'Filters',
    filterSub: 'Refine the results to fit you',
    labelExp: 'Experience level',
    labelType: 'Employment type',
    labelSkills: 'Key skills (weighted)',
    expLevels: { Entry: 'Entry level', Junior: 'Junior', Mid: 'Mid/Senior' },
    typeLevels: { 'Full-time': 'Full-time', Internship: 'Internship', Contract: 'Contract' },
    applyFilters: 'Apply filters',
    applyHint: 'Selected filters are applied when you start the analysis.',
    resetFilters: 'Reset',
    activeFilters: (n) => `${n} selected`,

    statTotal: 'Total jobs',
    statMatched: 'Matched jobs',
    statAvg: 'Average match score',
    statBest: 'Top match score',
    statTotalHint: 'In the database',
    statMatchedHint: 'With current filters',
    statAvgHint: 'Across results',
    statBestHint: 'Highest score',

    resultTitle: 'AI recommended matches',
    resultCount: (n) => `${n} result${n === 1 ? '' : 's'}`,
    sortLabel: 'Sort by',
    sortScore: 'Match score',
    sortSalary: 'Salary',
    sortSalaryDisabled: 'Salary (no data)',
    matchLabel: 'Match',
    scoreAria: (pct) => `Match score ${pct}%`,
    showDetail: 'Show detailed analysis',
    hideDetail: 'Hide detailed analysis',
    detailTitle: 'Detailed analysis',
    skillsTitle: 'Required skills',
    skillHit: 'Matches your selected skill',
    noSkills: 'No skill information listed.',
    noSummary: 'No summary available.',
    salaryUnknown: 'Salary not listed',
    rank: (n) => `#${n}`,

    emptyIdleTitle: 'No results yet',
    emptyIdleBody: 'Upload your resume (PDF), enter a target role and start the AI analysis.',
    emptyResultTitle: 'No matching results found',
    emptyResultBody: 'Try relaxing the filters or choosing a different location.',
    errorTitle: 'Could not load results',
    errFill: 'Please provide a PDF resume and a target role.',
    errNetwork: 'Cannot reach the server. Make sure the backend is running.',
    errServer: 'The request could not be processed.',
    errNotFound: 'Resume not found. Please upload it again.',
    errPdf: 'Only PDF files are supported.',
    retry: 'Try again',
    footer: 'Match results are AI estimates and for reference only.',
  },
}
