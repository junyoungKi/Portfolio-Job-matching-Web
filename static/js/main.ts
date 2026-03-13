// static/js/main.ts
export {}; 

interface Translation {
    title: string; subtitle: string; statsLabel: string;
    keywordPlaceholder: string; resumeLabel: string;
    btnStart: string; analyzing: string; resultTitle: string;
    clickToggle: string; matchLabel: string; filterToggle: string;
    locAll: string; labelExp: string; labelType: string; labelSkills: string;
    expEntry: string; expJunior: string; expMid: string;
    typeFull: string; typeIntern: string; typeContract: string;
    btnFile: string; noFile: string;
    matchError: string; alertFill: string;
}

interface JobMatch {
    title: string; company: string; location: string;
    salary: string; match_score: number;
    summary_ko: string; analysis_ko: string;
    summary_en: string; analysis_en: string;
    skills: string;
}

const translations: Record<string, Translation> = {
    ko: {
        title: "스마트 잡 AI", subtitle: "북미 커리어 매칭 시스템", statsLabel: "데이터베이스 공고 수",
        keywordPlaceholder: "희망 직무 (예: C++ 개발자)", resumeLabel: "이력서 업로드 (PDF)", 
        btnStart: "AI 분석 시작", analyzing: ">> 분석 중입니다...", resultTitle: "AI 추천 매칭 결과",
        clickToggle: "상세 분석 내용 보기/닫기", matchLabel: "매칭률", filterToggle: "고급 필터 (경력, 형태, 기술 스택)",
        locAll: "북미 전체", labelExp: "경력 수준", labelType: "고용 형태", labelSkills: "주요 기술 (가중치 적용)",
        expEntry: "신입 (Entry)", expJunior: "주니어", expMid: "미들/시니어",
        typeFull: "정규직", typeIntern: "인턴십", typeContract: "계약직",
        btnFile: "파일 선택", noFile: "선택된 파일 없음",
        matchError: "조건에 맞는 결과가 없습니다.", alertFill: "필수 정보를 입력해주세요!"
    },
    en: {
        title: "Smart Job AI", subtitle: "North America Career Matcher", statsLabel: "Jobs in Database",
        keywordPlaceholder: "Target Role (e.g. C++ Developer)", resumeLabel: "Upload Your Resume (PDF)", 
        btnStart: "START AI ANALYSIS", analyzing: ">> ANALYZING...", resultTitle: "AI Recommended Matches",
        clickToggle: "Click to toggle detailed analysis", matchLabel: "Match", filterToggle: "Advanced Filters (Level, Type, Skills)",
        locAll: "All North America", labelExp: "Experience Level", labelType: "Employment Type", labelSkills: "Key Skills (Weighted)",
        expEntry: "Entry Level", expJunior: "Junior", expMid: "Mid/Senior",
        typeFull: "Full-time", typeIntern: "Internship", typeContract: "Contract",
        btnFile: "Choose File", noFile: "No file chosen",
        matchError: "No matching results found.", alertFill: "Please fill in all required fields!"
    }
};

let currentMatches: JobMatch[] = [];
let openIndices: Set<number> = new Set();

const updateStats = async (): Promise<void> => {
    try {
        const res = await fetch('/stats');
        const data = await res.json();
        const el = document.getElementById('totalJobs');
        if (el) el.innerText = data.total_jobs.toLocaleString();
    } catch (e) { console.error(e); }
};

const changeUI = (): void => {
    const langSelect = document.getElementById('langSelect') as HTMLSelectElement;
    const lang = langSelect.value;
    const t = translations[lang];

    const updateText = (id: string, text: string) => {
        const el = document.getElementById(id);
        if (el) el.innerText = text;
    };

    updateText('ui-title', t.title);
    updateText('ui-subtitle', t.subtitle);
    updateText('ui-stats-label', t.statsLabel);
    updateText('ui-resume-label', t.resumeLabel);
    updateText('processBtn', t.btnStart);
    updateText('status', t.analyzing);
    updateText('ui-result-title', t.resultTitle);
    updateText('ui-filter-toggle', t.filterToggle);
    updateText('opt-loc-all', t.locAll);
    updateText('ui-label-exp', t.labelExp);
    updateText('ui-label-type', t.labelType);
    updateText('ui-label-skills', t.labelSkills);
    updateText('opt-exp-entry', t.expEntry);
    updateText('opt-exp-junior', t.expJunior);
    updateText('opt-exp-mid', t.expMid);
    updateText('opt-type-full', t.typeFull);
    updateText('opt-type-intern', t.typeIntern);
    updateText('opt-type-contract', t.typeContract); // 🎯 계약직 번역 적용
    updateText('btn-file-custom', t.btnFile);

    const keywordInput = document.getElementById('jobKeyword') as HTMLInputElement;
    if (keywordInput) keywordInput.placeholder = t.keywordPlaceholder;

    const fileInput = document.getElementById('resumeFile') as HTMLInputElement;
    const nameDisplay = document.getElementById('file-name-display');
    if (nameDisplay && (!fileInput.files || !fileInput.files.length)) {
        nameDisplay.innerText = t.noFile;
    }
};

// ... (handleFileSelect, processAll, fetchMatches 로직 동일하므로 생략 - 파일 참조) ...
const handleFileSelect = (): void => {
    const input = document.getElementById('resumeFile') as HTMLInputElement;
    const display = document.getElementById('file-name-display');
    const lang = (document.getElementById('langSelect') as HTMLSelectElement).value;
    if (display && input.files && input.files.length > 0) {
        display.innerText = input.files[0].name;
        display.classList.remove('text-gray-500', 'italic');
        display.classList.add('text-blue-400', 'font-bold');
    } else if (display) {
        display.innerText = translations[lang].noFile;
        display.classList.add('text-gray-500', 'italic');
    }
};

const processAll = async (): Promise<void> => {
    const fileInput = document.getElementById('resumeFile') as HTMLInputElement;
    const keywordInput = document.getElementById('jobKeyword') as HTMLInputElement;
    const locationSelect = document.getElementById('locationInput') as HTMLSelectElement;
    const lang = (document.getElementById('langSelect') as HTMLSelectElement).value;
    const file = fileInput.files ? fileInput.files[0] : null;
    if (!file || !keywordInput.value) return alert(translations[lang].alertFill);
    const formData = new FormData();
    formData.append('file', file);
    document.getElementById('status')?.classList.remove('hidden');
    try {
        const res = await fetch(`/process-resume?keyword=${encodeURIComponent(keywordInput.value)}&location=${encodeURIComponent(locationSelect.value)}`, { method: 'POST', body: formData });
        const data = await res.json();
        if (data.status === "success") { openIndices.clear(); await fetchMatches(data.id); }
    } finally { document.getElementById('status')?.classList.add('hidden'); updateStats(); }
};

const fetchMatches = async (resumeId: number): Promise<void> => {
    const getCheckedValues = (name: string) => Array.from(document.querySelectorAll(`input[name="${name}"]:checked`)).map(el => (el as HTMLInputElement).value);
    let url = `/match/${resumeId}?`;
    getCheckedValues("level").forEach(v => url += `levels=${encodeURIComponent(v)}&`);
    getCheckedValues("type").forEach(v => url += `types=${encodeURIComponent(v)}&`);
    getCheckedValues("skill").forEach(v => url += `skills=${encodeURIComponent(v)}&`);
    try {
        const res = await fetch(url);
        currentMatches = await res.json();
        displayResults(currentMatches);
    } catch (e) { console.error(e); }
};

const displayResults = (matches: JobMatch[]): void => {
    const list = document.getElementById('matchList');
    const lang = (document.getElementById('langSelect') as HTMLSelectElement).value;
    const t = translations[lang];
    document.getElementById('resultSection')?.classList.remove('hidden');
    if (!list) return;
    if (matches.length === 0) { list.innerHTML = `<div class="text-center p-12 text-gray-500 italic">${t.matchError}</div>`; return; }
    list.innerHTML = matches.map((job, idx) => {
        const summary = lang === 'ko' ? job.summary_ko : job.summary_en;
        const analysis = lang === 'ko' ? job.analysis_ko : job.analysis_en;
        const isHidden = openIndices.has(idx) ? "" : "hidden";
        return `
        <div class="bg-gray-800 rounded-3xl border border-gray-700 overflow-hidden mb-4 transition-all hover:border-blue-500/50">
            <div onclick="toggleDetail(${idx})" class="p-6 cursor-pointer hover:bg-gray-750 flex justify-between items-center">
                <div class="flex-1">
                    <div class="flex flex-wrap gap-2 mb-2">
                        <span class="text-blue-500 text-[10px] font-black uppercase bg-blue-500/10 px-2 py-0.5 rounded">${job.company}</span>
                        <span class="text-gray-400 text-[10px] font-bold"><i class="fa-solid fa-location-dot mr-1"></i>${job.location}</span>
                        <span class="text-green-500 text-[10px] font-mono font-bold">| ${job.salary}</span>
                    </div>
                    <h3 class="text-xl font-black text-white mb-2 leading-tight">${job.title}</h3>
                    <p class="text-gray-300 text-sm font-medium italic border-l-2 border-blue-500 pl-3 leading-relaxed">"${summary}"</p>
                </div>
                <div class="text-right ml-4">
                    <div class="text-3xl font-black text-white italic tracking-tighter">${(job.match_score*100).toFixed(1)}%</div>
                    <div class="text-[9px] text-gray-500 font-bold uppercase mt-1 tracking-widest">${t.matchLabel}</div>
                </div>
            </div>
            <div id="detail-${idx}" class="${isHidden} bg-gray-900/50 p-6 border-t border-gray-700/50">
                <p class="text-gray-400 text-sm leading-relaxed whitespace-pre-wrap font-light">${analysis}</p>
            </div>
            <div class="bg-gray-700/20 py-2 text-center text-[8px] text-gray-600 uppercase font-black cursor-pointer hover:text-gray-400" onclick="toggleDetail(${idx})">${t.clickToggle}</div>
        </div>
    `}).join('');
};

const toggleDetail = (idx: number): void => {
    const el = document.getElementById(`detail-${idx}`);
    if (!el) return;
    el.classList.toggle('hidden');
    if (el.classList.contains('hidden')) openIndices.delete(idx);
    else openIndices.add(idx);
};

const init = (): void => { updateStats(); changeUI(); };
const handleLanguageChange = (): void => { changeUI(); if (currentMatches.length > 0) displayResults(currentMatches); };

window.addEventListener('DOMContentLoaded', init);
(window as any).init = init;
(window as any).handleLanguageChange = handleLanguageChange;
(window as any).processAll = processAll;
(window as any).toggleDetail = toggleDetail;
(window as any).handleFileSelect = handleFileSelect;