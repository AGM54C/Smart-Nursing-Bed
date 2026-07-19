/**
 * 智能护理病床 - 鸿蒙APP HTTP 网络请求服务
 *
 * 封装 @ohos.net.http，统一处理:
 *   - JWT Bearer Token 自动注入
 *   - JSON 序列化/反序列化
 *   - 错误处理 + 超时
 *   - 日志
 */
import { http } from '@kit.NetworkKit';
import { SERVER_BASE_URL, PI_BASE_URL } from './Constants';

// ─── JWT Token 存储 (内存级, 重启后需重新登录) ───
let _jwtToken: string = '';

export function setToken(token: string): void {
  _jwtToken = token;
}

export function getToken(): string {
  return _jwtToken;
}

export function clearToken(): void {
  _jwtToken = '';
}

export function isLoggedIn(): boolean {
  return _jwtToken.length > 0;
}

// ─── 通用 HTTP 请求 ───

interface RequestOptions {
  method?: http.RequestMethod;
  body?: object;
  timeout?: number;        // ms
  baseUrl?: string;        // 默认 SERVER_BASE_URL
  noAuth?: boolean;        // 跳过JWT
}

export async function apiRequest<T>(path: string, options?: RequestOptions): Promise<T> {
  const method = options?.method ?? http.RequestMethod.GET;
  const baseUrl = options?.baseUrl ?? SERVER_BASE_URL;
  const timeout = options?.timeout ?? 15000;
  const url = baseUrl + path;

  const httpRequest = http.createHttp();

  // 构建 headers
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (!options?.noAuth && _jwtToken) {
    headers['Authorization'] = `Bearer ${_jwtToken}`;
  }

  try {
    const response = await httpRequest.request(url, {
      method: method,
      header: headers,
      extraData: options?.body ? JSON.stringify(options.body) : undefined,
      connectTimeout: timeout,
      readTimeout: timeout,
    });

    // HTTP 状态码检查
    const code = response.responseCode;
    if (code < 200 || code >= 300) {
      let errMsg = `HTTP ${code}`;
      try {
        const errBody = JSON.parse(response.result as string);
        errMsg = errBody.error || errMsg;
      } catch (e) { /* ignore parse error */ }
      throw new Error(errMsg);
    }

    // 解析 JSON
    const data = JSON.parse(response.result as string) as T;
    return data;

  } finally {
    httpRequest.destroy();
  }
}

// ─── 便捷方法 ───

export async function apiGet<T>(path: string): Promise<T> {
  return apiRequest<T>(path, { method: http.RequestMethod.GET });
}

export async function apiPost<T>(path: string, body: object): Promise<T> {
  return apiRequest<T>(path, { method: http.RequestMethod.POST, body });
}

export async function apiPut<T>(path: string, body: object): Promise<T> {
  return apiRequest<T>(path, { method: http.RequestMethod.PUT, body });
}

// ─── 树莓派直连请求 (不带JWT, 短超时) ───
export async function piRequest<T>(path: string, body?: object): Promise<T> {
  return apiRequest<T>(path, {
    method: body ? http.RequestMethod.POST : http.RequestMethod.GET,
    body,
    baseUrl: PI_BASE_URL,
    noAuth: true,
    timeout: 5000,
  });
}

// ─── 登录 ───

interface LoginResult {
  token: string;
  user: {
    id: number;
    username: string;
    role: string;
    real_name: string;
  };
}

export async function login(username: string, password: string): Promise<LoginResult> {
  const result = await apiRequest<LoginResult>('/api/auth/login', {
    method: http.RequestMethod.POST,
    body: { username, password },
    noAuth: true,
  });
  setToken(result.token);
  return result;
}

export function logout(): void {
  clearToken();
}
