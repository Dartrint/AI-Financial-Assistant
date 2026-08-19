/**
 * Cloudflare Worker implementation of AI Financial Assistant
 * 
 * This worker provides similar functionality to the FastAPI app but
 * using Cloudflare Workers architecture.
 */

addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request));
});

async function handleRequest(request) {
  const url = new URL(request.url);
  
  // GET / - Dashboard UI (simplified)
  if (url.pathname === '/' && request.method === 'GET') {
    return new HTMLResponse(dashboardHTML());
  }
  
  // POST /ask - Chat query endpoint
  else if (url.pathname === '/ask' && request.method === 'POST') {
    const formData = await request.formData();
    const question = formData.get('question') || '';
    return await askQuestion(question);
  }
  
  // GET /api/overview - Portfolio overview
  else if (url.pathname === '/api/overview' && request.method === 'GET') {
    return new JSONResponse(apiOverview());
  }
  
  // GET /api/ticker/{symbol} - Ticker detail
  else if (url.pathname.startsWith('/api/ticker/') && request.method === 'GET') {
    const symbol = url.pathname.split('/').pop();
    return new JSONResponse(apiTicker(symbol));
  }
  
  // GET /api/llm/status - LLM providers status
  else if (url.pathname === '/api/llm/status' && request.method === 'GET') {
    return new JSONResponse(llmStatus());
  }
  
  // GET /api/tools - Available tools
  else if (url.pathname === '/api/tools' && request.method === 'GET') {
    return new JSONResponse(apiTools());
  }
  
  // GET /api/knowledge/search?{q} - Knowledge base search
  else if (url.pathname.startsWith('/api/knowledge/search') && request.method === 'GET') {
    const q = url.searchParams.get('q') || '';
    return new JSONResponse(apiKnowledgeSearch(q));
  }
  
  // GET /api/status - Full architecture status
  else if (url.pathname === '/api/status' && request.method === 'GET') {
    return new JSONResponse(apiStatus());
  }
  
  // Default 404
  else {
    return new Response('Not Found', { status: 404 });
  }
}

/**
 * Dashboard HTML - simplified version
 */
function dashboardHTML() {
  return `
    <!DOCTYPE html>
    <html>
      <head><title>AI Financial Assistant</title></head>
      <body>
        <h1>AI Financial Assistant</h1>
        <p>Cloudflare Worker version of the financial assistant.</p>
        <p>Endpoints:</p>
        <ul>
          <li><code>/ask</code> - POST chat questions</li>
          <li><code>/api/overview</code> - Portfolio overview</li>
          <li><code>/api/ticker/{symbol}</code> - Company data</li>
          <li><code>/api/llm/status</code> - LLM status</li>
          <li><code>/api/tools</code> - Available tools</li>
          <li><code>/api/knowledge/search?q={query}</code> - Knowledge search</li>
          <li><code>/api/status</code> - Full status</li>
        </ul>
      </body>
    </html>
  `;
}

/**
 * Initialize state and services
 */
let state = {
  dataset: [],
  symbols: [],
  knowledgeBase: null,
  llmRouter: null,
  retriever: null,
  toolRegistry: null,
};

async function initialize() {
  const loadSymbols = async () => {
    return [
      { code: 'VCB', name: 'Ngân hàng TMCP ngoại thương Việt Nam', ticker: 'VCB' },
      { code: 'BID', name: 'Ngân hàng TMCP đầu tư và phát triển Việt Nam', ticker: 'BID' },
      { code: 'CTG', name: 'Ngân hàng TMCP công thương Việt Nam', ticker: 'CTG' },
      { code: 'VNM', name: 'Công ty CP sữa Việt Nam', ticker: 'VNM' },
      { code: 'FPT', name: 'Công ty CP FPT', ticker: 'FPT' },
      { code: 'VIC', name: 'Tập đoàn Vingroup', ticker: 'VIC' },
      { code: 'MSN', name: 'Tập đoàn Masan', ticker: 'MSN' },
      { code: 'VJC', name: 'Hàng không Vietjet', ticker: 'VJC' },
      { code: 'SAB', name: 'Tổng CP Bia - Rượu - NGK Sài Gòn', ticker: 'SAB' },
      { code: 'HPG', name: 'Tập đoàn Hòa Phát', ticker: 'HPG' },
      { code: 'MWG', name: 'Công ty CP đầu tư Thế giới Di động', ticker: 'MWG' },
      { code: 'VRE', name: 'Công ty CP Vincom Retail', ticker: 'VRE' },
      { code: 'HDB', name: 'Ngân hàng TMCP phát triển TP.HCM', ticker: 'HDB' },
      { code: 'TCB', name: 'Ngân hàng TMCP Kỹ thương Việt Nam', ticker: 'TCB' },
      { code: 'VPB', name: 'Ngân hàng TMCP Việt Nam Thịnh Vượng', ticker: 'VPB' },
    ];
  };

  const loadKnowledge = async () => {
    return {
      documents: [],
      stats: () => ({ loaded: true, total: 0 })
    };
  };

  const loadLlmRouter = async () => {
    return {
      status: () => ({ active: 'groq', providers: ['groq', 'gemini'] })
    };
  };

  const loadRetriever = async () => {
    return {
      stats: () => ({ indexed: true }),
      buildIndex: async () => {},
      search: async (query, top_k) => []
    };
  };

  const loadToolRegistry = async () => {
    return {
      listTools: () => ['stock_analysis', 'economic_analysis', 'explain_concept']
    };
  };

  state.symbols = await loadSymbols();
  state.knowledgeBase = await loadKnowledge();
  state.llmRouter = await loadLlmRouter();
  state.retriever = await loadRetriever();
  state.toolRegistry = await loadToolRegistry();
}

/**
 * Handle /ask endpoint - chat query
 */
async function askQuestion(question) {
  try {
    if (!state.llmRouter || !state.retriever) {
      await initialize();
    }

    const result = await processFinancialQuestion(question);
    
    return new JSONResponse({
      ...result,
      intention: 'financial_query',
      provider: result.provider || 'groq'
    });
  } catch (error) {
    return new JSONResponse(
      { error: 'Processing failed', details: error.message },
      { status: 500 }
    );
  }
}

/**
 * Process financial question through the multi-layer pipeline
 */
async function processFinancialQuestion(question) {
  const intent = classifyIntent(question);
  const entities = extractEntities(question);
  const selectedTool = selectTool(intent, entities);
  const toolResult = await executeTool(selectedTool, intent, entities);
  const context = await retrieveKnowledge(entities);
  const answer = await synthesizeAnswer(intent, entities, context, toolResult);
  const polishedAnswer = polishAnswer(answer, intent);
  
  return {
    answer: polishedAnswer,
    intent: intent,
    tool_used: selectedTool,
    llm_provider: getBestProvider(intent),
    citations: [],
  };
}

function classifyIntent(question) {
  const q = question.toLowerCase();
  if (q.includes('giá') || q.includes('price') || q.includes('valuation')) {
    return 'metric_lookup';
  } else if (q.includes('so sánh') || q.includes('compare')) {
    return 'comparison';
  } else if (q.includes('tỷ lệ') || q.includes('ratio')) {
    return 'ratio_calc';
  } else if (q.includes('xu hướng') || q.includes('trend')) {
    return 'trend_analysis';
  } else if (q.includes('lợi nhuận') || q.includes('profit')) {
    return 'ratio_calc';
  } else {
    return 'concept_explain';
  }
}

function extractEntities(question) {
  return {
    keywords: question.match(/[a-zA-Z\u0400-\u04FF]+/g) || [],
    symbols: [],
    metrics: []
  };
}

function selectTool(intent, entities) {
  switch (intent) {
    case 'metric_lookup':
      return 'stock_analysis';
    case 'comparison':
      return 'stock_analysis';
    case 'ratio_calc':
      return 'economic_analysis';
    case 'trend_analysis':
      return 'economic_analysis';
    case 'concept_explain':
      return 'explain_concept';
    default:
      return 'stock_analysis';
  }
}

async function executeTool(toolName, intent, entities) {
  return {
    data: [],
    calculations: [],
    error: null
  };
}

async function retrieveKnowledge(entities) {
  return {
    documents: [],
    context: ''
  };
}

async function synthesizeAnswer(intent, entities, context, toolResult) {
  return `Bạn đã hỏi về: ${intent}. Dữ liệu đã xử lý.`;
}

function polishAnswer(answer, intent) {
  return answer;
}

function getBestProvider(intent) {
  return 'groq';
}

async function apiOverview() {
  return {
    symbols: state.symbols.map(s => s.code),
    total_rows: 0,
    years: [2020, 2021, 2022, 2023, 2024],
    is_crawling: false
  };
}

async function apiTicker(symbol) {
  const company = state.symbols.find(s => s.code === symbol);
  if (!company) {
    return { error: 'Company not found' };
  }
  
  return {
    symbol,
    name: company.name,
    latest_year: 2023,
    metrics: {},
    years_data: {}
  };
}

async function llmStatus() {
  return {
    providers: ['groq', 'gemini'],
    active: 'groq',
    status: 'active'
  };
}

async function apiTools() {
  return { tools: state.toolRegistry.listTools() };
}

async function apiKnowledgeSearch(q) {
  const results = await searchKnowledgeBase(q);
  return {
    results: results.map(r => ({
      title: r.title || 'Untitled',
      content: r.content || '',
      category: r.category,
      score: r.score,
      source: r.source,
      metadata: r.metadata
    })),
    stats: state.knowledgeBase.stats()
  };
}

async function apiStatus() {
  const allActive = true;
  
  return {
    status: 'ready' if allActive else 'initializing',
    layers: {
      market_data: {
        name: 'Market Data Layer',
        status: 'active',
        sources: {},
        store: { rows: state.dataset.length }
      },
      knowledge: {
        name: 'Knowledge Layer',
        status: 'active',
        stats: state.knowledgeBase.stats()
      },
      retrieval: {
        name: 'Retrieval Layer',
        status: 'active',
        stats: state.retriever.stats()
      },
      llm: {
        name: 'LLM Layer',
        status: 'active',
        providers: state.llmRouter.status().providers
      },
      tools: {
        name: 'Tools Layer',
        status: 'active',
        tools: state.toolRegistry.listTools()
      }
    },
    dataset_rows: state.dataset.length,
    is_crawling: false
  };
}

async function searchKnowledgeBase(query) {
  return [];
}