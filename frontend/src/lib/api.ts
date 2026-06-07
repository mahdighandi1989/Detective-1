// frontend/src/lib/api.ts

// --- Type Definitions (Derived from project description and assumed backend schemas) ---

/**
 * Interface for user login credentials.
 */
export interface UserLogin {
  username: string;
  password: string;
}

/**
 * Interface for the authentication token response.
 */
export interface Token {
  access_token: string;
  token_type: string;
}

/**
 * Interface for a Person profile.
 */
export interface Person {
  id: string;
  name: string;
  photo_url?: string; // URL to the person's photo
  current_position?: string;
  past_positions: string[];
  background: string; // General background information
  risk_assessment: RiskAssessment;
  related_article_ids: string[]; // IDs of related encyclopedia articles
  created_at: string;
  updated_at: string;
}

/**
 * Interface for creating a new Person profile.
 */
export interface PersonCreate {
  name: string;
  photo_url?: string;
  current_position?: string;
  past_positions?: string[];
  background?: string;
}

/**
 * Interface for updating an existing Person profile.
 */
export interface PersonUpdate extends Partial<PersonCreate> {}

/**
 * Interface for an Encyclopedia Article.
 */
export interface Article {
  id: string;
  title: string;
  content: string; // Raw or processed content
  category: string; // e.g., "نفوذ", "ضد جاسوسی"
  summary?: string; // LLM-generated summary
  source_url?: string;
  source_credibility_score?: number; // 0-100, backend-calculated
  created_at: string;
  updated_at: string;
}

/**
 * Interface for creating a new Encyclopedia Article.
 */
export interface ArticleCreate {
  title: string;
  content: string;
  category: string;
  source_url?: string;
}

/**
 * Interface for updating an existing Encyclopedia Article.
 */
export interface ArticleUpdate extends Partial<ArticleCreate> {}

/**
 * Interface for a Person's risk assessment.
 */
export interface RiskAssessment {
  score: number; // e.g., 0-100
  category: 'پاک' | 'مشکوک' | 'نفوذی' | 'استحاله_یافته';
}

/**
 * Interface for Graph data, assuming a simple nodes and edges structure
 * suitable for React Flow / Cytoscape.js.
 */
export interface GraphData {
  nodes: { id: string; label: string; riskCategory: RiskAssessment['category']; [key: string]: any }[];
  edges: { id: string; source: string; target: string; label?: string; [key: string]: any }[];
}


// --- API Configuration ---
// Use environment variable for the backend API base URL.
// NEXT_PUBLIC_ prefix is required for client-side environment variables in Next.js.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1';

// --- Helper for API Calls ---
/**
 * Generic fetcher function to handle API requests, including authentication and error handling.
 * @param url The API endpoint path (e.g., '/persons/').
 * @param method The HTTP method (GET, POST, PUT, DELETE).
 * @param token Optional JWT token for authorization.
 * @param body Optional request body for POST/PUT requests.
 * @returns A promise that resolves to the parsed JSON response.
 * @throws An error if the network request fails or the response status is not OK.
 */
async function fetcher<T>(
  url: string,
  method: 'GET' | 'POST' | 'PUT' | 'DELETE',
  token?: string,
  body?: object
): Promise<T> {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const config: RequestInit = {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  };

  try {
    const response = await fetch(`${API_BASE_URL}${url}`, config);

    if (!response.ok) {
      // Attempt to parse error details from response body
      const errorData = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(errorData.detail || `API Error: ${response.statusText}`);
    }

    // Handle cases where response body might be empty (e.g., 204 No Content)
    if (response.status === 204 || response.headers.get('content-length') === '0') {
      return {} as T; // Return an empty object or a specific success type if T expects it.
    }

    return await response.json() as T;
  } catch (error) {
    console.error(`Error in fetcher for ${url} (${method}):`, error);
    throw error; // Re-throw to allow calling functions to handle it
  }
}

// --- Authentication API ---
/**
 * Logs in a user and returns an authentication token.
 * Assumes FastAPI's OAuth2PasswordRequestForm expects 'application/x-www-form-urlencoded'.
 * @param credentials User's username and password.
 * @returns A promise that resolves to a Token object.
 */
export async function loginUser(credentials: UserLogin): Promise<Token> {
  const formBody = new URLSearchParams();
  formBody.append('username', credentials.username);
  formBody.append('password', credentials.password);

  const headers: HeadersInit = {
    'Content-Type': 'application/x-www-form-urlencoded',
  };

  try {
    const response = await fetch(`${API_BASE_URL}/auth/token`, {
      method: 'POST',
      headers,
      body: formBody.toString(),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(errorData.detail || `Login failed: ${response.statusText}`);
    }

    return await response.json() as Token;
  } catch (error) {
    console.error('Error logging in:', error);
    throw error;
  }
}

// --- Persons API ---
/**
 * Fetches a list of all person profiles.
 * @param token JWT token for authorization.
 * @returns A promise that resolves to an array of Person objects.
 */
export async function getPersons(token: string): Promise<Person[]> {
  return fetcher<Person[]>('/persons/', 'GET', token);
}

/**
 * Fetches a single person profile by ID.
 * @param id The ID of the person.
 * @param token JWT token for authorization.
 * @returns A promise that resolves to a Person object.
 */
export async function getPersonById(id: string, token: string): Promise<Person> {
  return fetcher<Person>(`/persons/${id}`, 'GET', token);
}

/**
 * Creates a new person profile.
 * @param data The data for the new person.
 * @param token JWT token for authorization.
 * @returns A promise that resolves to the newly created Person object.
 */
export async function createPerson(data: PersonCreate, token: string): Promise<Person> {
  return fetcher<Person>('/persons/', 'POST', token, data);
}

/**
 * Updates an existing person profile.
 * @param id The ID of the person to update.
 * @param data The updated data for the person.
 * @param token JWT token for authorization.
 * @returns A promise that resolves to the updated Person object.
 */
export async function updatePerson(id: string, data: PersonUpdate, token: string): Promise<Person> {
  return fetcher<Person>(`/persons/${id}`, 'PUT', token, data);
}

/**
 * Deletes a person profile by ID.
 * @param id The ID of the person to delete.
 * @param token JWT token for authorization.
 * @returns A promise that resolves to a confirmation message.
 */
export async function deletePerson(id: string, token: string): Promise<{ message: string }> {
  return fetcher<{ message: string }>(`/persons/${id}`, 'DELETE', token);
}

// --- Encyclopedia API ---
/**
 * Fetches a list of all encyclopedia articles, with optional keyword search.
 * @param token JWT token for authorization.
 * @param query Optional search query to filter articles.
 * @returns A promise that resolves to an array of Article objects.
 */
export async function getEncyclopediaArticles(token: string, query?: string): Promise<Article[]> {
  const url = query ? `/encyclopedia/articles/?q=${encodeURIComponent(query)}` : '/encyclopedia/articles/';
  return fetcher<Article[]>(url, 'GET', token);
}

/**
 * Fetches a single encyclopedia article by ID.
 * @param id The ID of the article.
 * @param token JWT token for authorization.
 * @returns A promise that resolves to an Article object.
 */
export async function getEncyclopediaArticleById(id: string, token: string): Promise<Article> {
  return fetcher<Article>(`/encyclopedia/articles/${id}`, 'GET', token);
}

/**
 * Creates a new encyclopedia article.
 * @param data The data for the new article.
 * @param token JWT token for authorization.
 * @returns A promise that resolves to the newly created Article object.
 */
export async function createEncyclopediaArticle(data: ArticleCreate, token: string): Promise<Article> {
  return fetcher<Article>('/encyclopedia/articles/', 'POST', token, data);
}

/**
 * Updates an existing encyclopedia article.
 * @param id The ID of the article to update.
 * @param data The updated data for the article.
 * @param token JWT token for authorization.
 * @returns A promise that resolves to the updated Article object.
 */
export async function updateEncyclopediaArticle(id: string, data: ArticleUpdate, token: string): Promise<Article> {
  return fetcher<Article>(`/encyclopedia/articles/${id}`, 'PUT', token, data);
}

/**
 * Deletes an encyclopedia article by ID.
 * @param id The ID of the article to delete.
 * @param token JWT token for authorization.
 * @returns A promise that resolves to a confirmation message.
 */
export async function deleteEncyclopediaArticle(id: string, token: string): Promise<{ message: string }> {
  return fetcher<{ message: string }>(`/encyclopedia/articles/${id}`, 'DELETE', token);
}

/**
 * Performs a semantic search on encyclopedia articles using a query.
 * Assumes a backend endpoint that takes a query and returns relevant articles.
 * @param query The natural language query for semantic search.
 * @param token JWT token for authorization.
 * @returns A promise that resolves to an array of matching Article objects.
 */
export async function semanticSearchArticles(query: string, token: string): Promise<Article[]> {
  // Assuming the backend has a specific endpoint for semantic search, e.g., /encyclopedia/semantic-search
  // and it expects a POST request with a query in the body.
  return fetcher<Article[]>('/encyclopedia/semantic-search', 'POST', token, { query });
}

// --- Graph API ---
/**
 * Fetches data for the relationship graph.
 * @param token JWT token for authorization.
 * @returns A promise that resolves to GraphData containing nodes and edges.
 */
export async function getGraphData(token: string): Promise<GraphData> {
  // Assuming a /graph/data endpoint that returns nodes and edges
  return fetcher<GraphData>('/graph/data', 'GET', token);
}