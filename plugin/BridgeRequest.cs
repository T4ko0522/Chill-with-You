using System;
using System.IO;
using System.Net;
using System.Text;
using System.Threading.Tasks;

namespace ChillWithYou.Spotify
{
    // Unity's release-player HTTP policy does not apply to this loopback client.
    // No Unity objects are accessed by the worker thread.
    internal sealed class BridgeRequest : IDisposable
    {
        private readonly HttpWebRequest _request;
        private readonly Task<Response> _task;

        internal sealed class Response
        {
            public bool Success;
            public string Text;
            public string Error;
        }

        public BridgeRequest(string url, string token, string body = null)
        {
            Uri uri = new Uri(url);
            if (uri.Scheme != "http" || uri.Host != "127.0.0.1" ||
                (uri.AbsolutePath != "/state" && uri.AbsolutePath != "/command"))
            {
                throw new ArgumentException("Bridge requests must target the local Spotify bridge.");
            }
            _request = (HttpWebRequest)WebRequest.Create(uri);
            _request.Proxy = null;
            _request.AllowAutoRedirect = false;
            _request.Timeout = 2000;
            _request.ReadWriteTimeout = 2000;
            _request.KeepAlive = false;
            _request.ServicePoint.Expect100Continue = false;
            _request.Headers["Authorization"] = "Bearer " + token;
            _request.Method = body == null ? "GET" : "POST";
            _task = Task.Run(() => Execute(body));
        }

        public bool IsCompleted { get { return _task.IsCompleted; } }
        public Response Result { get { return _task.Result; } }

        private Response Execute(string body)
        {
            try
            {
                if (body != null)
                {
                    byte[] bytes = Encoding.UTF8.GetBytes(body);
                    _request.ContentType = "application/json";
                    _request.ContentLength = bytes.Length;
                    using (Stream stream = _request.GetRequestStream())
                    {
                        stream.Write(bytes, 0, bytes.Length);
                    }
                }
                using (HttpWebResponse response = (HttpWebResponse)_request.GetResponse())
                using (Stream stream = response.GetResponseStream())
                using (MemoryStream buffer = new MemoryStream())
                {
                    byte[] chunk = new byte[4096];
                    int count;
                    while ((count = stream.Read(chunk, 0, chunk.Length)) > 0)
                    {
                        if (buffer.Length + count > 65536)
                        {
                            throw new IOException("Bridge response exceeded 64 KiB.");
                        }
                        buffer.Write(chunk, 0, count);
                    }
                    int status = (int)response.StatusCode;
                    return new Response {
                        Success = status >= 200 && status < 300,
                        Text = Encoding.UTF8.GetString(buffer.ToArray()),
                        Error = status >= 200 && status < 300 ? null : "HTTP " + status
                    };
                }
            }
            catch (WebException error)
            {
                if (error.Response != null) error.Response.Close();
                return new Response { Success = false, Error = error.Message };
            }
            catch (Exception error)
            {
                return new Response { Success = false, Error = error.Message };
            }
        }

        public void Dispose()
        {
            _request.Abort();
        }
    }
}
