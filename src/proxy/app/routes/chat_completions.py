""" chat completion routes """

from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# pylint: disable=E0402
from ..config import Deployment
from ..openai_async import OpenAIAsyncManager
from .request_manager import RequestManager

import sys
import json
import httpx

class ChatCompletionsRequest(BaseModel):
    """OpenAI Chat Request"""

    messages: list[dict[str, str]]
    dataSources: list[Any] | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    n: int | None = None
    stream: bool = False
    top_p: float | None = None
    stop: str | list[str] | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    functions: list[dict[str, Any]] | None = None
    function_call: str | dict[str, str] | None = None


class ChatCompletions(RequestManager):
    """Completion route"""

    def include_router(self):
        """include router"""

        # Support for Python Azure OpenAI SDK 1.0+
        @self.router.post(
            "/deployments/{deployment_name}/chat/completions",
            status_code=200,
            response_model=None,
        )
        # Support for .NET Azure OpenAI Service SDK
        @self.router.post(
            "/openai/deployments/{deployment_name}/chat/completions",
            status_code=200,
            response_model=None,
        )
        # Support for .NET Azure OpenAI Extensions Chat Completions
        @self.router.post(
            "/openai/deployments/{deployment_name}/extensions/chat/completions",
            status_code=200,
            response_model=None,
        )
        async def oai_chat_completion(
            model: ChatCompletionsRequest,
            request: Request,
            response: Response,
            deployment_name: str = None,
        ) -> Any:
            """OpenAI chat completion response"""

            if "extension" in request.url.path:
                self.is_extension = True

            completion, status_code = await self.process_request(
                deployment_name=deployment_name,
                request=request,
                model=model,
                call_method=self.call_openai_chat,
                validate_method=self.__validate_chat_completion_request,
            )

            if isinstance(completion, AsyncGenerator):
                return StreamingResponse(completion)

            # function_callingの応答がある場合の処理を追加
            if 'function_call' in completion['choices'][0]['message']:
                func_name = completion['choices'][0]['message']['function_call']['name']
                args = json.loads(completion['choices'][0]['message']['function_call']['arguments'])
                #print(f"name: {func_name}, args:{args}", file=sys.stderr)

                # function_callingに対応する実際の関数リスト
                func_list=[self.search_hotels, self.search_restaurants]
                # 関数名とそのインデックスをマッピングする辞書を作成
                func_dict = {func.__name__: idx for idx, func in enumerate(func_list)}

                if func_name in func_dict:
                    print(f"function {func_name} matched", file=sys.stderr)
                    # フロントエンドの表示を制御するため、function_call 応答を削除
                    del completion['choices'][0]['message']['function_call']
                    completion['choices'][0]['message']["finish_reason"] = "stop"                    
                    # レスポンスに関数の結果を返す
                    try:
                        completion['choices'][0]['message']['content'] = await func_list[func_dict[func_name]](**args)
                    except:
                        print(f"function error", file=sys.stderr)

            #print(completion, file=sys.stderr)

            response.status_code = status_code
            return completion

        return self.router

    async def call_openai_chat(self, model: object, deployment: Deployment) -> Any:
        """call openai with retry"""

        if self.is_extension:
            url = (
                f"{deployment.endpoint_url}/openai/deployments/"
                f"{deployment.deployment_name}/extensions/chat/completions"
                f"?api-version={self.api_version}"
            )
        else:
            url = (
                f"{deployment.endpoint_url}/openai/deployments/"
                f"{deployment.deployment_name}/chat/completions"
                f"?api-version={self.api_version}"
            )

        openai_request = self.model_to_dict(model)
        async_mgr = OpenAIAsyncManager(deployment)

        if model.stream:
            response, http_status_code = await async_mgr.async_post_streaming(openai_request, url)
        else:
            response, http_status_code = await async_mgr.async_openai_post(openai_request, url)

        return response, http_status_code

    def __validate_chat_completion_request(self, model: ChatCompletionsRequest):
        """validate input"""

        # check the max_tokens is between 1 and 4000
        if model.max_tokens is not None and not 1 <= model.max_tokens <= 4000:
            self.report_exception("Oops, max_tokens must be between 1 and 4000.", 400)

        if model.n is not None and not 1 <= model.n <= 10:
            self.throw_validation_error("Oops, n must be between 1 and 10.", 400)

        # check the temperature is between 0 and 1
        if model.temperature is not None and not 0 <= model.temperature <= 1:
            self.report_exception("Oops, temperature must be between 0 and 1.", 400)

        # check the top_p is between 0 and 1
        if model.top_p is not None and not 0 <= model.top_p <= 1:
            self.report_exception("Oops, top_p must be between 0 and 1.", 400)

        # check the frequency_penalty is between 0 and 1
        if model.frequency_penalty is not None and not 0 <= model.frequency_penalty <= 1:
            self.report_exception("Oops, frequency_penalty must be between 0 and 1.", 400)

        # check the presence_penalty is between 0 and 1
        if model.presence_penalty is not None and not 0 <= model.presence_penalty <= 1:
            self.report_exception("Oops, presence_penalty must be between 0 and 1.", 400)

    async def search_hotels(self, **args)  -> Any:
            """search_hotels関数の定義。引数をプリントするだけ。"""
            location = args["location"]
            price = args["price"]
            features = args["features"]
            print(httpx.post('http://search-hotels', json=args), file=sys.stderr)
            #print(f"ARO Hotel をお勧めします(Searching for hotels in {location}, with max price {price}, and features {features})", file=sys.stdout)
            return f"ARO Hotel をお勧めします (引数: {args})" #(Searching for hotels in {location}, with max price {price}, and features {features})"

    async def search_restaurants(self, **args)  -> Any:
            category = args["category"]
            budget = args["budget"]
            print(httpx.post('http://search-restaurants', json=args), file=sys.stderr)
            return f"AOAI レストランをお勧めします (引数: {args})" #(Searching for restaurants with category is {category}, budget in {budget})"
