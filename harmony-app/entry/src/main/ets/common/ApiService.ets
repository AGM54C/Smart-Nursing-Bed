/**
 * 智能护理病床 - 鸿蒙APP HTTP 网络请求服务 (ArkTS Strict Mode)
 */
import { http } from '@kit.NetworkKit';
import { SERVER_BASE_URL, PI_BASE_URL } from './Constants';

// ─── JWT Token 存储 ───
let _jwtToken: string = '';

export function setToken(token: string): void { _jwtToken = token; }
export function getToken(): string { return _jwtToken; }
export function clearToken(): void { _jwtToken = ''; }
export function isLoggedIn(): boolean { return _jwtToken.length > 0; }

// ─── 请求配置类 ───
export class RequestOptions {
  method: http.RequestMethod = http.RequestMethod.GET;
  body: string = '';
  timeout: number = 15000;
  baseUrl: string = SERVER_BASE_URL;
  noAuth: boolean = false;
}

// ─── 登录结果类 ───
export class LoginUser {
  id: number = 0;
  username: string = '';
  role: string = '';
  real_name: string = '';
}

export class LoginResult {
  token: string = '';
  user: LoginUser = new LoginUser();
}

// ─── 通用请求体类 ───
export class RequestBody {
  action: string = '';
  params: string = '';
  text: string = '';
  username: string = '';
  password: string = '';
  patient_id: number = 0;
  question: string = '';
  status: string = '';
  room: string = '';
}

// ─── 通用响应类 ───
export class SimpleResponse {
  status: string = '';
  message: string = '';
}

export class NlcResponse {
  action: string = '';
  params: string = '';
  response: string = '';
  executed: boolean = false;
}

export class ConsultResponse {
  agent: string = '';
  agent_icon: string = '';
  response: string = '';
  patient_name: string = '';
}

// ─── 通用 HTTP 请求 ───
export async function apiRequest(path: string, options: RequestOptions): Promise<string> {
  const url = options.baseUrl + path;
  const httpRequest = http.createHttp();

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (!options.noAuth && _jwtToken.length > 0) {
    headers['Authorization'] = `Bearer ${_jwtToken}`;
  }

  try {
    const response = await httpRequest.request(url, {
      method: options.method,
      header: headers,
      extraData: options.body.length > 0 ? options.body : undefined,
      connectTimeout: options.timeout,
      readTimeout: options.timeout,
    });

    const code = response.responseCode;
    if (code < 200 || code >= 300) {
      throw new Error(`HTTP ${code}`);
    }

    return response.result as string;
  } finally {
    httpRequest.destroy();
  }
}

// ─── 便捷方法 ───

export async function apiGet(path: string): Promise<string> {
  const opts = new RequestOptions();
  opts.method = http.RequestMethod.GET;
  return apiRequest(path, opts);
}

export async function apiPost(path: string, body: string): Promise<string> {
  const opts = new RequestOptions();
  opts.method = http.RequestMethod.POST;
  opts.body = body;
  return apiRequest(path, opts);
}

export async function apiPut(path: string, body: string): Promise<string> {
  const opts = new RequestOptions();
  opts.method = http.RequestMethod.PUT;
  opts.body = body;
  return apiRequest(path, opts);
}

// ─── 树莓派直连请求 ───
export async function piRequest(path: string, body: string): Promise<string> {
  const opts = new RequestOptions();
  opts.method = http.RequestMethod.POST;
  opts.body = body;
  opts.baseUrl = PI_BASE_URL;
  opts.noAuth = true;
  opts.timeout = 5000;
  return apiRequest(path, opts);
}

// ─── 登录 ───
export async function login(username: string, password: string): Promise<LoginResult> {
  const bodyObj = new RequestBody();
  bodyObj.username = username;
  bodyObj.password = password;

  const opts = new RequestOptions();
  opts.method = http.RequestMethod.POST;
  opts.body = JSON.stringify(bodyObj);
  opts.noAuth = true;

  const raw = await apiRequest('/api/auth/login', opts);
  const result: LoginResult = JSON.parse(raw) as LoginResult;
  setToken(result.token);
  return result;
}

export function logout(): void {
  clearToken();
}
