// Copyright (c) 2025 GenOrca (by zenoengine). All Rights Reserved.

#include "MCPythonTcpServer.h"
#include "Sockets.h"
#include "SocketSubsystem.h"
#include "IPAddress.h"
#include "Common/TcpListener.h"
#include "IPythonScriptPlugin.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonReader.h"
#include "MCPythonHelper.h"
#include "Dom/JsonObject.h"
#include "ILiveCodingModule.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/ScopeLock.h"

DEFINE_LOG_CATEGORY_STATIC(LogMCPython, Log, All);

namespace
{
    // Accumulates lines emitted under the LogLiveCoding log category while a live
    // coding compile runs. Live Coding dispatches compiler output from worker threads,
    // so Serialize must be callable from any thread.
    class FMCPCompileLogCapture : public FOutputDevice
    {
    public:
        virtual void Serialize(const TCHAR* Message, ELogVerbosity::Type Verbosity, const FName& Category) override
        {
            static const FName TargetCategory(TEXT("LogLiveCoding"));
            if (Category != TargetCategory)
                return;
            FScopeLock Guard(&LineLock);
            CapturedLines.Add(FString(Message));
        }

        virtual bool CanBeUsedOnAnyThread() const override { return true; }

        // Returns all captured lines joined by newlines and clears the buffer.
        FString GetAndClear()
        {
            FScopeLock Guard(&LineLock);
            FString Result = FString::Join(CapturedLines, TEXT("\n"));
            CapturedLines.Reset();
            return Result;
        }

    private:
        FCriticalSection LineLock;
        TArray<FString> CapturedLines;
    };

    FString LCCompileResultToString(ELiveCodingCompileResult Result)
    {
        switch (Result)
        {
        case ELiveCodingCompileResult::Success:            return TEXT("Success");
        case ELiveCodingCompileResult::NoChanges:          return TEXT("NoChanges");
        case ELiveCodingCompileResult::Failure:            return TEXT("Failure");
        case ELiveCodingCompileResult::CompileStillActive: return TEXT("CompileStillActive");
        case ELiveCodingCompileResult::NotStarted:         return TEXT("NotStarted");
        case ELiveCodingCompileResult::Cancelled:          return TEXT("Cancelled");
        case ELiveCodingCompileResult::InProgress:         return TEXT("InProgress");
        default:                                           return TEXT("Unknown");
        }
    }

    // Reads UBT's Log.txt if it was written during this compile (detected by comparing
    // the file's modification time before and after the compile call) and returns lines
    // that look like MSVC compiler diagnostics.  MSVC writes errors and warnings in the
    // form  "file(line): error/warning/fatal error CNNNN: ..."  which is a well-known
    // public format, independent of any specific engine implementation.
    FString CollectUBTDiagnostics(const FString& UBTLogFilePath, const FDateTime& TimestampBefore)
    {
        const FDateTime TimestampAfter = IFileManager::Get().GetTimeStamp(*UBTLogFilePath);
        if (TimestampAfter == FDateTime::MinValue() || TimestampAfter == TimestampBefore)
            return FString();

        FString LogContent;
        if (!FFileHelper::LoadFileToString(LogContent, *UBTLogFilePath))
            return FString();

        TArray<FString> AllLines;
        LogContent.ParseIntoArrayLines(AllLines, /*bCullEmpty=*/true);

        TArray<FString> DiagnosticLines;
        for (const FString& Line : AllLines)
        {
            // Match the standard MSVC diagnostic format: path(row,col): severity CXXXX:
            const bool bError   = Line.Contains(TEXT("): error "));
            const bool bFatal   = Line.Contains(TEXT("): fatal error "));
            const bool bWarning = Line.Contains(TEXT("): warning "));
            if (bError || bFatal || bWarning)
                DiagnosticLines.Add(Line);
        }

        return FString::Join(DiagnosticLines, TEXT("\n"));
    }
}

// Helper function to convert FJsonValue to Python literal string
FString ConvertJsonValueToPythonLiteral(const TSharedPtr<FJsonValue>& JsonVal)
{
    if (!JsonVal.IsValid() || JsonVal->Type == EJson::Null) return TEXT("None");

    switch (JsonVal->Type)
    {
        case EJson::String:
        {
            FString EscapedString = JsonVal->AsString();
            // Order of replacement is important.
            // Escape backslashes: "\" -> "\\"
            EscapedString = EscapedString.Replace(TEXT("\\"), TEXT("\\\\"));
            // Escape single quotes: ' -> \'
            EscapedString = EscapedString.Replace(TEXT("\'"), TEXT("\\\'"));
            // Escape double quotes: \" -> \\\"
            EscapedString = EscapedString.Replace(TEXT("\""), TEXT("\\\""));
            // Escape newlines: \n -> \\n
            EscapedString = EscapedString.Replace(TEXT("\n"), TEXT("\\n"));
            // Escape carriage returns: \r -> \\r
            EscapedString = EscapedString.Replace(TEXT("\r"), TEXT("\\r"));
            // Escape tabs: \t -> \\t
            EscapedString = EscapedString.Replace(TEXT("\t"), TEXT("\\t"));
            return FString::Printf(TEXT("\'%s\'"), *EscapedString);
        }
        case EJson::Number:
            return JsonVal->AsString();
        case EJson::Boolean:
            return JsonVal->AsBool() ? TEXT("True") : TEXT("False");
        case EJson::Array:
        {
            FString ArrayLiteral = TEXT("[");
            const auto& Array = JsonVal->AsArray();
            for (int32 i = 0; i < Array.Num(); ++i) {
                ArrayLiteral += ConvertJsonValueToPythonLiteral(Array[i]);
                if (i < Array.Num() - 1) ArrayLiteral += TEXT(", ");
            }
            ArrayLiteral += TEXT("]");
            return ArrayLiteral;
        }
        case EJson::Object:
        {
            FString DictLiteral = TEXT("{");
            const auto& Object = JsonVal->AsObject();
            bool bFirst = true;
            for (const auto& Pair : Object->Values) {
                if (!bFirst) DictLiteral += TEXT(", ");
                
                // UE 5.7: FJsonObject::Values key is FString; UE 5.8: UE::FSharedString.
                // operator* yields const TCHAR* on both, so this builds on either engine.
                FString KeyString = *Pair.Key;
                // Escape key string as well (similar to EJson::String case)
                KeyString = KeyString.Replace(TEXT("\\"), TEXT("\\\\"));
                KeyString = KeyString.Replace(TEXT("\'"), TEXT("\\\'"));
                KeyString = KeyString.Replace(TEXT("\""), TEXT("\\\""));
                KeyString = KeyString.Replace(TEXT("\n"), TEXT("\\n"));
                KeyString = KeyString.Replace(TEXT("\r"), TEXT("\\r"));
                KeyString = KeyString.Replace(TEXT("\t"), TEXT("\\t"));

                DictLiteral += FString::Printf(TEXT("\'%s\': %s"), *KeyString, *ConvertJsonValueToPythonLiteral(Pair.Value));
                bFirst = false;
            }
            DictLiteral += TEXT("}");
            return DictLiteral;
        }
        default:
            return TEXT("None");
    }
}

FMCPythonTcpServer::FMCPythonTcpServer()
{
    RegisterNativeHandlers();
}
FMCPythonTcpServer::~FMCPythonTcpServer() { Stop(); }

void FMCPythonTcpServer::RegisterNativeHandlers()
{
    NativeHandlers.Add(TEXT("livecoding_compile"), [this](TSharedPtr<FJsonObject> JsonObj, FSocket* ClientSocket)
    {
        HandleLiveCodingCompile(JsonObj, ClientSocket);
    });
}

void FMCPythonTcpServer::SendJsonResponse(TSharedPtr<FJsonObject> ResponseJson, FSocket* ClientSocket, bool bCloseSocket)
{
	FString ResultJson;
	TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&ResultJson);
	FJsonSerializer::Serialize(ResponseJson.ToSharedRef(), Writer);
	Writer->Close();

	FTCHARToUTF8 ResultUtf8(*ResultJson);
	const uint8* DataPtr = (const uint8*)ResultUtf8.Get();
	int32 TotalSize = ResultUtf8.Length();
	int32 TotalSent = 0;
	while (TotalSent < TotalSize)
	{
		int32 SentNow = 0;
		if (!ClientSocket->Send(DataPtr + TotalSent, TotalSize - TotalSent, SentNow))
		{
			break;
		}
		if (SentNow == 0)
		{
			break;
		}
		TotalSent += SentNow;
	}

	if (bCloseSocket)
	{
		ClientSocket->Close();
		ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(ClientSocket);
	}
}

bool FMCPythonTcpServer::Start(const FString& InIP, uint16 InPort)
{
    FIPv4Address IPAddr;
    FIPv4Address::Parse(InIP, IPAddr);
    FIPv4Endpoint Endpoint(IPAddr, InPort);

    TcpListener = MakeShared<FTcpListener>(Endpoint, FTimespan::FromMilliseconds(100), false);
    TcpListener->OnConnectionAccepted().BindRaw(this, &FMCPythonTcpServer::HandleIncomingConnection);

    bShouldRun = true;
    UE_LOG(LogMCPython, Log, TEXT("TCP server started at %s:%d."), *InIP, InPort);
    return true;
}

void FMCPythonTcpServer::Stop()
{
	bShouldRun = false;
	TcpListener.Reset();
	UE_LOG(LogMCPython, Log, TEXT("TCP server stopped."));
}

bool FMCPythonTcpServer::HandleIncomingConnection(FSocket* ClientSocket, const FIPv4Endpoint& ClientEndpoint)
{
    UE_LOG(LogMCPython, Verbose, TEXT("Incoming connection from %s"), *ClientEndpoint.ToString());

    AsyncTask(ENamedThreads::AnyBackgroundThreadNormalTask, [this, ClientSocket, ClientEndpoint]() {
        TArray<uint8> ReceivedData;

        // Wait (bounded) for the client to actually send something. Liveness
        // probes connect and close without sending a byte — the old
        // `while (HasPendingData || ReceivedData.IsEmpty())` loop hot-spun a
        // background worker forever per such connection, eventually starving
        // the AnyBackgroundThread pool and freezing ALL request processing
        // (connections still got accepted/logged by the listener thread, but
        // nothing was ever handled).
        if (!ClientSocket->Wait(ESocketWaitConditions::WaitForRead, FTimespan::FromSeconds(5)))
        {
            ClientSocket->Close();
            ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(ClientSocket);
            return;
        }

        uint32 DataSize = 0;
        while (ClientSocket->HasPendingData(DataSize))
        {
            TArray<uint8> Buffer;
            Buffer.SetNumZeroed(DataSize);
            int32 BytesRead = 0;
            if (!ClientSocket->Recv(Buffer.GetData(), Buffer.Num(), BytesRead) || BytesRead <= 0)
            {
                break;
            }
            Buffer.SetNum(BytesRead);
            ReceivedData.Append(Buffer);
        }

        // Connect-and-close probe (or peer reset): nothing to process.
        if (ReceivedData.IsEmpty())
        {
            ClientSocket->Close();
            ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(ClientSocket);
            return;
        }
        ReceivedData.Add(NULL);

        FString ReceivedString = FString(UTF8_TO_TCHAR(reinterpret_cast<const char*>(ReceivedData.GetData())));

        AsyncTask(ENamedThreads::GameThread, [this, ReceivedString, ClientSocket, ClientEndpoint]() {
            ProcessDataOnGameThread(ReceivedString, ClientSocket, ClientEndpoint);
        });
    });

    return true;
}

void FMCPythonTcpServer::ProcessDataOnGameThread(const FString& Data, FSocket* ClientSocket, const FIPv4Endpoint& ClientEndpoint)
{
    UE_LOG(LogMCPython, Verbose, TEXT("Processing Data on Game Thread: %s"), *Data);

    TSharedPtr<FJsonObject> JsonObj;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Data);
    FString TypeField;
    FString CodeField;
    FString ResultMsg;
    bool bExecSuccess = false;

    if (FJsonSerializer::Deserialize(Reader, JsonObj) && JsonObj.IsValid())
    {
        if (JsonObj->TryGetStringField(TEXT("type"), TypeField))
        {
            if (TypeField == TEXT("python"))
            {
                if (!JsonObj->TryGetStringField(TEXT("code"), CodeField))
                {
                    ResultMsg = TEXT("Failed: 'code' field missing for type 'python'");
                    CodeField = TEXT("import json; print(json.dumps({'success': False, 'message': 'Error: code field missing'}))");
                }
            }
            else if (TypeField == TEXT("python_call"))
            {
                FString ModuleName, FunctionName;
                if (JsonObj->TryGetStringField(TEXT("module"), ModuleName) &&
                    JsonObj->TryGetStringField(TEXT("function"), FunctionName))
                {
                    const TSharedPtr<FJsonObject>* ArgsJsonObjectPtr = nullptr; // Changed from TArray<TSharedPtr<FJsonValue>>*
                    JsonObj->TryGetObjectField(TEXT("args"), ArgsJsonObjectPtr); // Changed from TryGetArrayField

                    FString PyArgsStringForCall;
                    if (ArgsJsonObjectPtr && ArgsJsonObjectPtr->IsValid()) // Check if the pointer and the object it points to are valid
                    {
                        // Wrap the FJsonObject in an FJsonValueObject to pass to ConvertJsonValueToPythonLiteral
                        TSharedPtr<FJsonValueObject> ArgsJsonValue = MakeShareable(new FJsonValueObject(*ArgsJsonObjectPtr));
                        PyArgsStringForCall = ConvertJsonValueToPythonLiteral(ArgsJsonValue);
                    }
                    else
                    {
                        PyArgsStringForCall = TEXT("{}"); // Default to an empty Python dictionary string if "args" is not a valid object or is missing
                    }

                    // Generate a short script to call the execute_action function from the mcp_unreal_actions module
                    // The first argument is the target module name, the second is the target function name, and the third is the argument dictionary.
                    CodeField = FString::Printf(TEXT("import unreal;from UnrealMCPython import mcp_unreal_actions;unreal.MCPythonHelper.submit_result(mcp_unreal_actions.execute_action(\'%s\', \'%s\', %s));"), // result handed back via SubmitResult, NOT print (print echoed every response into the Output Log)
                                                *ModuleName, 
                                                *FunctionName, 
                                                *PyArgsStringForCall); 

                    UE_LOG(LogMCPython, Verbose, TEXT("Generated Python Call (via execute_action):\\n%s"), *CodeField);
                }
                else
                {
                    ResultMsg = TEXT("Failed: Missing 'module' or 'function' field for type 'python_call'");
                    CodeField = TEXT("import json; print(json.dumps({'success': False, 'message': 'Error: module/function field missing'}))");
                }
            }
            else if (FNativeCommandHandler* Handler = NativeHandlers.Find(TypeField))
            {
                (*Handler)(JsonObj, ClientSocket);
                return;
            }
            else
            {
                ResultMsg = FString::Printf(TEXT("Failed: Unsupported type: %s"), *TypeField);
                FString EscapedTypeField = TypeField.Replace(TEXT("\'"), TEXT("\\\'"));
                CodeField = FString::Printf(TEXT("import json; print(json.dumps({'success': False, 'message': 'Unsupported type: %s'}))"), *EscapedTypeField);
            }

            if (IPythonScriptPlugin::Get())
            {
                UMCPythonHelper::ClearSubmittedResult();
                LogCapture.Clear();
                GLog->AddOutputDevice(&LogCapture);
                
                FPythonCommandEx PythonCommand;
                PythonCommand.Command = CodeField;
                PythonCommand.ExecutionMode = EPythonCommandExecutionMode::ExecuteFile;

                bExecSuccess = IPythonScriptPlugin::Get()->ExecPythonCommandEx(PythonCommand);
                
                GLog->RemoveOutputDevice(&LogCapture);

                // Prefer the directly-submitted result (clean transport, nothing
                // echoed to the log). Fall back to the print/log capture for code
                // paths that still print (error stubs, legacy).
                FString CapturedLogs;
                if (!UMCPythonHelper::ConsumeSubmittedResult(CapturedLogs))
                {
                    CapturedLogs = LogCapture.GetLogs().TrimStartAndEnd();
                }

                bool bIsJson = false;
                if (CapturedLogs.StartsWith(TEXT("{")) || CapturedLogs.StartsWith(TEXT("["))) {
                    bIsJson = true;
                }
                if (!bIsJson) {
                    TSharedPtr<FJsonObject> ErrorJson = MakeShareable(new FJsonObject);
                    ErrorJson->SetBoolField(TEXT("success"), false);
                    ErrorJson->SetStringField(TEXT("message"), TEXT("Python did not return JSON"));
                    ErrorJson->SetStringField(TEXT("raw_result"), CapturedLogs);
                    FString WrappedJson;
                    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&WrappedJson);
                    FJsonSerializer::Serialize(ErrorJson.ToSharedRef(), Writer);
                    Writer->Close();
                    CapturedLogs = WrappedJson;
                }

                UE_LOG(LogMCPython, Verbose, TEXT("Python Command Executed. Success: %s. Output Log: %s"),
                    bExecSuccess ? TEXT("True") : TEXT("False"), *CapturedLogs);

                TSharedPtr<FJsonObject> ResponseToClient = MakeShareable(new FJsonObject);
                ResponseToClient->SetBoolField(TEXT("success"), bExecSuccess); // Overall success of ExecPythonCommandEx
                
                if (!ResultMsg.IsEmpty()) // If there was a pre-execution error message (e.g. bad JSON input from client)
                {
                     ResponseToClient->SetStringField(TEXT("message"), ResultMsg);
                }
                else if (!bExecSuccess) // Python execution itself failed
                {
                    if (!CapturedLogs.IsEmpty())
                    {
                        // If execution failed and logs are available, they likely contain the Python error
                        ResponseToClient->SetStringField(TEXT("message"), TEXT("Python execution failed. See result for details."));
                    }
                    else
                    {
                        // If execution failed and no logs, it's a more generic failure
                        ResponseToClient->SetStringField(TEXT("message"), TEXT("Python execution failed with no specific error log."));
                    }
                }
                else // bExecSuccess is true
                {
                     ResponseToClient->SetStringField(TEXT("message"), TEXT("Python command executed successfully."));
                }
                
                // The "result" field will contain whatever the Python script printed.
                ResponseToClient->SetStringField(TEXT("result"), CapturedLogs);

                FString ResultJson;
                TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&ResultJson);
                FJsonSerializer::Serialize(ResponseToClient.ToSharedRef(), Writer);
                Writer->Close();

                FTCHARToUTF8 ResultUtf8(*ResultJson);
                const uint8* DataPtr = (const uint8*)ResultUtf8.Get();
                int32 TotalSize = ResultUtf8.Length();
                int32 TotalSent = 0;
                while (TotalSent < TotalSize)
                {
                    int32 SentNow = 0;
                    if (!ClientSocket->Send(DataPtr + TotalSent, TotalSize - TotalSent, SentNow))
                    {
                        break; // Error occurred
                    }
                    if (SentNow == 0)
                    {
                        break; // Connection closed or can't send more
                    }
                    TotalSent += SentNow;
                }
            }
            else
            {
                ResultMsg = TEXT("Failed: PythonScriptPlugin not found");
                TSharedPtr<FJsonObject> ErrorResponse = MakeShareable(new FJsonObject);
                ErrorResponse->SetBoolField(TEXT("success"), false);
                ErrorResponse->SetStringField(TEXT("message"), ResultMsg);
                FString ErrorJson;
                TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&ErrorJson);
                FJsonSerializer::Serialize(ErrorResponse.ToSharedRef(), Writer);
                Writer->Close();
                FTCHARToUTF8 ResultUtf8(*ErrorJson);
                const uint8* DataPtr = (const uint8*)ResultUtf8.Get();
                int32 TotalSize = ResultUtf8.Length();
                int32 TotalSent = 0;
                while (TotalSent < TotalSize)
                {
                    int32 SentNow = 0;
                    if (!ClientSocket->Send(DataPtr + TotalSent, TotalSize - TotalSent, SentNow))
                    {
                        break;
                    }
                    if (SentNow == 0)
                    {
                        break;
                    }
                    TotalSent += SentNow;
                }
            }
        }
        else
        {
            ResultMsg = TEXT("Failed: Missing 'type' field in JSON request");
            TSharedPtr<FJsonObject> ErrorResponse = MakeShareable(new FJsonObject);
            ErrorResponse->SetBoolField(TEXT("success"), false);
            ErrorResponse->SetStringField(TEXT("message"), ResultMsg);
            FString ErrorJson;
            TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&ErrorJson);
            FJsonSerializer::Serialize(ErrorResponse.ToSharedRef(), Writer);
            Writer->Close();
            FTCHARToUTF8 ResultUtf8(*ErrorJson);
            const uint8* DataPtr = (const uint8*)ResultUtf8.Get();
            int32 TotalSize = ResultUtf8.Length();
            int32 TotalSent = 0;
            while (TotalSent < TotalSize)
            {
                int32 SentNow = 0;
                if (!ClientSocket->Send(DataPtr + TotalSent, TotalSize - TotalSent, SentNow))
                {
                    break;
                }
                if (SentNow == 0)
                {
                    break;
                }
                TotalSent += SentNow;
            }
        }
    }
    else
    {
        ResultMsg = TEXT("Failed: JSON parse error on received data");
        TSharedPtr<FJsonObject> ErrorResponse = MakeShareable(new FJsonObject);
        ErrorResponse->SetBoolField(TEXT("success"), false);
        ErrorResponse->SetStringField(TEXT("message"), ResultMsg);
        ErrorResponse->SetStringField(TEXT("raw_data"), Data);
        FString ErrorJson;
        TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&ErrorJson);
        FJsonSerializer::Serialize(ErrorResponse.ToSharedRef(), Writer);
        Writer->Close();
        FTCHARToUTF8 ResultUtf8(*ErrorJson);
        const uint8* DataPtr = (const uint8*)ResultUtf8.Get();
        int32 TotalSize = ResultUtf8.Length();
        int32 TotalSent = 0;
        while (TotalSent < TotalSize)
        {
            int32 SentNow = 0;
            if (!ClientSocket->Send(DataPtr + TotalSent, TotalSize - TotalSent, SentNow))
            {
                break;
            }
            if (SentNow == 0)
            {
                break;
            }
            TotalSent += SentNow;
        }
    }

    ClientSocket->Close();
    ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(ClientSocket);
}

void FMCPythonTcpServer::HandleLiveCodingCompile(TSharedPtr<FJsonObject> JsonObj, FSocket* ClientSocket)
{
    ILiveCodingModule* LiveCoding = FModuleManager::GetModulePtr<ILiveCodingModule>(TEXT("LiveCoding"));
    if (!LiveCoding)
    {
        TSharedPtr<FJsonObject> Response = MakeShareable(new FJsonObject);
        Response->SetBoolField(TEXT("success"), false);
        Response->SetStringField(TEXT("message"), TEXT("LiveCoding module is not available."));
        SendJsonResponse(Response, ClientSocket);
        return;
    }

    if (!LiveCoding->IsEnabledForSession())
    {
        TSharedPtr<FJsonObject> Response = MakeShareable(new FJsonObject);
        Response->SetBoolField(TEXT("success"), false);
        Response->SetStringField(TEXT("message"), TEXT("LiveCoding is not enabled for this session. Enable it in Editor Preferences > Live Coding."));
        SendJsonResponse(Response, ClientSocket);
        return;
    }

    const FString UBTLogPath = FPaths::Combine(FPaths::EngineDir(), TEXT("Programs"), TEXT("UnrealBuildTool"), TEXT("Log.txt"));
    const FDateTime UBTLogTimestampBefore = IFileManager::Get().GetTimeStamp(*UBTLogPath);

    FMCPCompileLogCapture CompileCapture;
    GLog->AddOutputDevice(&CompileCapture);

    UE_LOG(LogMCPython, Log, TEXT("LiveCoding compile started (WaitForCompletion)..."));
    const double StartTime = FPlatformTime::Seconds();

    ELiveCodingCompileResult CompileResult = ELiveCodingCompileResult::NotStarted;
    const bool bStarted = LiveCoding->Compile(ELiveCodingCompileFlags::WaitForCompletion, &CompileResult);

    GLog->RemoveOutputDevice(&CompileCapture);

    const double ElapsedTime = FPlatformTime::Seconds() - StartTime;
    const bool bSuccess = bStarted &&
        (CompileResult == ELiveCodingCompileResult::Success ||
         CompileResult == ELiveCodingCompileResult::NoChanges);

    UE_LOG(LogMCPython, Log, TEXT("LiveCoding compile finished in %.1fs: %s"),
        ElapsedTime, *LCCompileResultToString(CompileResult));

    FString Message;
    switch (CompileResult)
    {
    case ELiveCodingCompileResult::Success:
        Message = FString::Printf(TEXT("Compilation succeeded in %.1f seconds."), ElapsedTime);
        break;
    case ELiveCodingCompileResult::NoChanges:
        Message = FString::Printf(TEXT("Compilation finished in %.1f seconds (no changes detected)."), ElapsedTime);
        break;
    case ELiveCodingCompileResult::Failure:
        Message = FString::Printf(TEXT("Compilation failed in %.1f seconds. See compile_output for details."), ElapsedTime);
        break;
    case ELiveCodingCompileResult::Cancelled:
        Message = TEXT("Compilation was cancelled.");
        break;
    case ELiveCodingCompileResult::CompileStillActive:
        Message = TEXT("A prior compilation is still in progress.");
        break;
    case ELiveCodingCompileResult::NotStarted:
        Message = TEXT("Compilation could not be started (Live Coding monitor failed to launch).");
        break;
    default:
        Message = FString::Printf(TEXT("Compilation ended with result: %s"), *LCCompileResultToString(CompileResult));
        break;
    }

    TSharedPtr<FJsonObject> Response = MakeShareable(new FJsonObject);
    Response->SetBoolField(TEXT("success"), bSuccess);
    Response->SetStringField(TEXT("compile_result"), LCCompileResultToString(CompileResult));
    Response->SetStringField(TEXT("message"), Message);
    Response->SetNumberField(TEXT("elapsed_seconds"), ElapsedTime);

    const FString CapturedLog = CompileCapture.GetAndClear();
    if (!CapturedLog.IsEmpty())
        Response->SetStringField(TEXT("compile_output"), CapturedLog);

    const FString Diagnostics = CollectUBTDiagnostics(UBTLogPath, UBTLogTimestampBefore);
    if (!Diagnostics.IsEmpty())
        Response->SetStringField(TEXT("compiler_diagnostics"), Diagnostics);

    SendJsonResponse(Response, ClientSocket);
}