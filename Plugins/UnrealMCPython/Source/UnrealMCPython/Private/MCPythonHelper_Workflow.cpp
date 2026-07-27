// Copyright (c) 2025 GenOrca. All Rights Reserved.

#include "MCPythonHelper.h"

#include "AssetRegistry/AssetData.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Containers/Ticker.h"
#include "Editor.h"
#include "Editor/Transactor.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformTime.h"
#include "Misc/App.h"
#include "Misc/DateTime.h"
#include "Misc/EngineVersion.h"
#include "Misc/PackageName.h"
#include "Misc/ScopedSlowTask.h"
#include "Misc/StringBuilder.h"
#include "Modules/ModuleManager.h"
#include "ScopedTransaction.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "UObject/Package.h"
#include "UObject/UObjectGlobals.h"

DEFINE_LOG_CATEGORY_STATIC(LogWorkflowLease, Log, All);

namespace
{
    enum class EWorkflowLeasePhase : uint8
    {
        Idle,
        Atomic
    };

    struct FWorkflowLease
    {
        int32 TotalSteps = 1;
        int32 CompletedSteps = 0;
        double LastHeartbeatSeconds = 0.0;
        double IdleTimeoutSeconds = 60.0;
        EWorkflowLeasePhase Phase = EWorkflowLeasePhase::Idle;
        bool bHasSuccessfulWrite = false;
        bool bCancelRequested = false;
        TUniquePtr<FScopedSlowTask> SlowTask;
        FTSTicker::FDelegateHandle TickerHandle;
    };

    TUniquePtr<FScopedTransaction> GActiveWorkflowTransaction;
    TUniquePtr<FWorkflowLease> GWorkflowLease;
    FString GActiveWorkflowTransactionId;
    int32 GActiveWorkflowTransactionIndex = INDEX_NONE;
    FGuid GActiveWorkflowTransactionGuid;
    FString GLastCommittedWorkflowTransactionId;
    int32 GLastCommittedWorkflowTransactionIndex = INDEX_NONE;
    FGuid GLastCommittedWorkflowTransactionGuid;
    TSharedPtr<FJsonObject> GLastWorkflowRecovery;
    const FGuid GWorkflowEditorSessionId = FGuid::NewGuid();

    const FTransaction* TransactionAtIndex(int32 TransactionIndex)
    {
        if (!GEditor || !GEditor->Trans || TransactionIndex < 0 ||
            TransactionIndex >= GEditor->Trans->GetQueueLength())
        {
            return nullptr;
        }
        return GEditor->Trans->GetTransaction(TransactionIndex);
    }

    FGuid TransactionGuidAtIndex(int32 TransactionIndex)
    {
        const FTransaction* Transaction = TransactionAtIndex(TransactionIndex);
        return Transaction
            ? Transaction->GetContext().TransactionId
            : FGuid();
    }

    bool IsCurrentWorkflowTransaction(
        int32 TransactionIndex,
        const FGuid& TransactionGuid)
    {
        if (!GEditor || !GEditor->Trans || !TransactionGuid.IsValid())
        {
            return false;
        }
        const int32 CurrentUndoIndex =
            GEditor->Trans->GetQueueLength() -
            GEditor->Trans->GetUndoCount() - 1;
        const FTransaction* Transaction =
            TransactionAtIndex(TransactionIndex);
        return CurrentUndoIndex == TransactionIndex &&
            Transaction && !Transaction->HasExpired() &&
            Transaction->GetContext().TransactionId == TransactionGuid;
    }

    FString SerializeObject(const TSharedRef<FJsonObject>& Object)
    {
        FString Result;
        const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Result);
        FJsonSerializer::Serialize(Object, Writer);
        return Result;
    }

    FString ErrorResponse(const FString& Message, int32 TransactionIndex = INDEX_NONE)
    {
        const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
        Result->SetBoolField(TEXT("success"), false);
        Result->SetStringField(TEXT("message"), Message);
        Result->SetNumberField(TEXT("transaction_index"), TransactionIndex);
        Result->SetBoolField(TEXT("transaction_recorded"), false);
        Result->SetBoolField(TEXT("undo_available"), false);
        Result->SetBoolField(TEXT("undo_attempted"), false);
        Result->SetBoolField(TEXT("undo_succeeded"), false);
        return SerializeObject(Result);
    }

    FString TransactionResponse(
        const FString& TransactionId,
        int32 TransactionIndex,
        bool bUndoAttempted,
        bool bUndoSucceeded,
        bool bTransactionRecorded = false,
        bool bUndoAvailable = false)
    {
        const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
        Result->SetBoolField(TEXT("success"), !bUndoAttempted || bUndoSucceeded);
        Result->SetStringField(TEXT("transaction_id"), TransactionId);
        Result->SetNumberField(TEXT("transaction_index"), TransactionIndex);
        Result->SetBoolField(TEXT("transaction_recorded"), bTransactionRecorded);
        Result->SetBoolField(TEXT("undo_available"), bUndoAvailable);
        Result->SetBoolField(TEXT("undo_attempted"), bUndoAttempted);
        Result->SetBoolField(TEXT("undo_succeeded"), bUndoSucceeded);
        if (bUndoAttempted && !bUndoSucceeded)
        {
            Result->SetStringField(TEXT("message"), TEXT("Unreal did not undo the transaction."));
        }
        return SerializeObject(Result);
    }

    FString LeasePhaseName()
    {
        if (!GWorkflowLease)
        {
            return TEXT("none");
        }
        return GWorkflowLease->Phase == EWorkflowLeasePhase::Atomic
            ? TEXT("atomic")
            : TEXT("idle");
    }

    bool IsLeaseCancelRequested()
    {
        return GWorkflowLease &&
            (GWorkflowLease->bCancelRequested ||
             (GWorkflowLease->SlowTask &&
              GWorkflowLease->SlowTask->ShouldCancel()));
    }

    TSharedRef<FJsonObject> WorkflowLeaseObject()
    {
        const TSharedRef<FJsonObject> Lease = MakeShared<FJsonObject>();
        Lease->SetBoolField(
            TEXT("active"),
            GActiveWorkflowTransaction.IsValid() && GWorkflowLease.IsValid());
        Lease->SetStringField(
            TEXT("transaction_id"),
            GWorkflowLease ? GActiveWorkflowTransactionId : FString());
        Lease->SetStringField(TEXT("phase"), LeasePhaseName());
        Lease->SetNumberField(
            TEXT("completed_steps"),
            GWorkflowLease ? GWorkflowLease->CompletedSteps : 0);
        Lease->SetNumberField(
            TEXT("total_steps"),
            GWorkflowLease ? GWorkflowLease->TotalSteps : 0);
        Lease->SetBoolField(
            TEXT("cancel_requested"), IsLeaseCancelRequested());
        Lease->SetBoolField(
            TEXT("has_successful_write"),
            GWorkflowLease && GWorkflowLease->bHasSuccessfulWrite);
        Lease->SetBoolField(
            TEXT("watchdog_registered"),
            GWorkflowLease && GWorkflowLease->TickerHandle.IsValid());
        if (GLastWorkflowRecovery)
        {
            Lease->SetObjectField(TEXT("last_recovery"), GLastWorkflowRecovery);
        }
        else
        {
            Lease->SetField(
                TEXT("last_recovery"), MakeShared<FJsonValueNull>());
        }
        return Lease;
    }

    FString LeaseResponse(bool bSuccess, const FString& Message = FString())
    {
        const TSharedRef<FJsonObject> Result = WorkflowLeaseObject();
        Result->SetBoolField(TEXT("success"), bSuccess);
        if (!Message.IsEmpty())
        {
            Result->SetStringField(TEXT("message"), Message);
        }
        return SerializeObject(Result);
    }

    void ClearActiveWorkflowIdentifiers()
    {
        GActiveWorkflowTransactionId.Empty();
        GActiveWorkflowTransactionIndex = INDEX_NONE;
        GActiveWorkflowTransactionGuid.Invalidate();
    }

    void ClearWorkflowLease(bool bRemoveTicker = true)
    {
        if (!GWorkflowLease)
        {
            return;
        }
        if (bRemoveTicker && GWorkflowLease->TickerHandle.IsValid())
        {
            FTSTicker::RemoveTicker(GWorkflowLease->TickerHandle);
        }
        GWorkflowLease->TickerHandle.Reset();
        GWorkflowLease->SlowTask.Reset();
        GWorkflowLease.Reset();
    }

    FString RecoverExpiredWorkflowLease(bool bFromTicker)
    {
        if (!GActiveWorkflowTransaction || !GWorkflowLease)
        {
            return ErrorResponse(TEXT("No workflow transaction lease is active."));
        }

        const FString TransactionId = GActiveWorkflowTransactionId;
        const int32 TransactionIndex = GActiveWorkflowTransactionIndex;
        const FGuid TransactionGuid = GActiveWorkflowTransactionGuid;
        const bool bHadSuccessfulWrite =
            GWorkflowLease->bHasSuccessfulWrite;
        FString Outcome;
        FString Message;
        bool bRecoverySucceeded = false;

        if (!bHadSuccessfulWrite)
        {
            GActiveWorkflowTransaction->Cancel();
            GActiveWorkflowTransaction.Reset();
            Outcome = TEXT("cancelled_no_write");
            Message = TEXT(
                "Workflow lease timed out before a successful write; "
                "the transaction was cancelled.");
            bRecoverySucceeded = true;
        }
        else
        {
            GActiveWorkflowTransaction.Reset();
            const bool bTransactionRecorded =
                IsCurrentWorkflowTransaction(TransactionIndex, TransactionGuid);
            const bool bUndoSucceeded =
                bTransactionRecorded && GEditor->UndoTransaction();
            if (bUndoSucceeded)
            {
                Outcome = TEXT("rolled_back");
                Message = TEXT(
                    "Workflow lease timed out and its transaction was rolled back.");
                bRecoverySucceeded = true;
            }
            else
            {
                Outcome = TEXT("manual_recovery_required");
                Message = FString::Printf(
                    TEXT("Workflow lease '%s' timed out, but guarded undo "
                         "was refused. Inspect the editor before continuing."),
                    *TransactionId);
                UE_LOG(LogWorkflowLease, Error, TEXT("%s"), *Message);
            }
        }

        const TSharedRef<FJsonObject> Recovery = MakeShared<FJsonObject>();
        Recovery->SetStringField(TEXT("transaction_id"), TransactionId);
        Recovery->SetStringField(TEXT("outcome"), Outcome);
        Recovery->SetBoolField(TEXT("success"), bRecoverySucceeded);
        Recovery->SetNumberField(TEXT("transaction_index"), TransactionIndex);
        Recovery->SetStringField(TEXT("message"), Message);
        Recovery->SetStringField(
            TEXT("recovered_at"), FDateTime::UtcNow().ToIso8601());
        GLastWorkflowRecovery = Recovery;

        ClearActiveWorkflowIdentifiers();
        ClearWorkflowLease(!bFromTicker);

        const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
        Result->SetBoolField(TEXT("success"), false);
        Result->SetBoolField(TEXT("timed_out"), true);
        Result->SetBoolField(
            TEXT("recovery_succeeded"), bRecoverySucceeded);
        Result->SetStringField(TEXT("transaction_id"), TransactionId);
        Result->SetStringField(TEXT("recovery_outcome"), Outcome);
        Result->SetStringField(TEXT("message"), Message);
        return SerializeObject(Result);
    }

    bool TickWorkflowLease()
    {
        if (!GWorkflowLease || !GActiveWorkflowTransaction)
        {
            return false;
        }
        if (GWorkflowLease->Phase == EWorkflowLeasePhase::Atomic)
        {
            return true;
        }
        const double IdleSeconds =
            FPlatformTime::Seconds() -
            GWorkflowLease->LastHeartbeatSeconds;
        if (IdleSeconds <= GWorkflowLease->IdleTimeoutSeconds)
        {
            return true;
        }
        RecoverExpiredWorkflowLease(true);
        return false;
    }

    FString PackageFilename(const FString& PackageName)
    {
        FString Filename = FPackageName::LongPackageNameToFilename(
            PackageName, FPackageName::GetAssetPackageExtension());
        if (!IFileManager::Get().FileExists(*Filename))
        {
            Filename = FPackageName::LongPackageNameToFilename(
                PackageName, FPackageName::GetMapPackageExtension());
        }
        return Filename;
    }
}

FString UMCPythonHelper::GetWorkflowEditorContext(const TArray<FString>& AssetPaths)
{
    const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("project_id"), FApp::GetProjectName());
    Result->SetStringField(
        TEXT("editor_session_id"),
        GWorkflowEditorSessionId.ToString(EGuidFormats::DigitsWithHyphensLower));
    Result->SetStringField(TEXT("engine_version"), FEngineVersion::Current().ToString());

    FString CurrentMap;
    if (GEditor)
    {
        if (const UWorld* World = GEditor->GetEditorWorldContext().World())
        {
            if (const UPackage* Package = World->GetOutermost())
            {
                CurrentMap = Package->GetName();
            }
        }
    }
    Result->SetStringField(TEXT("current_map"), CurrentMap);

    FAssetRegistryModule& AssetRegistryModule =
        FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry"));
    const IAssetRegistry& AssetRegistry = AssetRegistryModule.Get();
    const TSharedRef<FJsonObject> Fingerprints = MakeShared<FJsonObject>();

    for (const FString& AssetPath : AssetPaths)
    {
        const FString PackageName = FPackageName::ObjectPathToPackageName(AssetPath);
        const FName PackageFName(*PackageName);
        const TOptional<FAssetPackageData> PackageData =
            AssetRegistry.GetAssetPackageDataCopy(PackageFName);
        TArray<FAssetData> AssetsInPackage;
        AssetRegistry.GetAssetsByPackageName(
            PackageFName, AssetsInPackage, false);
        const TSharedRef<FJsonObject> Fingerprint = MakeShared<FJsonObject>();
        Fingerprint->SetStringField(TEXT("asset_path"), AssetPath);
        Fingerprint->SetBoolField(TEXT("exists"), !AssetsInPackage.IsEmpty());

        if (PackageData.IsSet())
        {
            TStringBuilder<40> HashBuilder;
            HashBuilder << PackageData->GetPackageSavedHash();
            Fingerprint->SetStringField(
                TEXT("package_guid"), FString(HashBuilder.ToString()));
            Fingerprint->SetNumberField(
                TEXT("disk_size"), static_cast<double>(PackageData->DiskSize));
            const FString Filename = PackageFilename(PackageName);
            if (IFileManager::Get().FileExists(*Filename))
            {
                Fingerprint->SetStringField(
                    TEXT("modified_time"),
                    IFileManager::Get().GetTimeStamp(*Filename).ToIso8601());
            }
        }

        const UPackage* LoadedPackage = FindPackage(nullptr, *PackageName);
        Fingerprint->SetBoolField(
            TEXT("dirty"), LoadedPackage && LoadedPackage->IsDirty());
        Fingerprints->SetObjectField(AssetPath, Fingerprint);
    }

    Result->SetObjectField(TEXT("asset_fingerprints"), Fingerprints);
    Result->SetObjectField(
        TEXT("workflow_transaction"), WorkflowLeaseObject());
    return SerializeObject(Result);
}

FString UMCPythonHelper::BeginWorkflowTransaction(
    const FString& TransactionId,
    const FString& Description,
    int32 TotalSteps,
    bool bShowDialog,
    float IdleTimeoutSeconds)
{
    if (GActiveWorkflowTransaction)
    {
        return ErrorResponse(FString::Printf(
            TEXT("Transaction '%s' is already active."),
            *GActiveWorkflowTransactionId));
    }
    if (TransactionId.IsEmpty() || Description.IsEmpty())
    {
        return ErrorResponse(TEXT("Transaction id and description are required."));
    }
    if (TotalSteps <= 0)
    {
        return ErrorResponse(TEXT("Total steps must be positive."));
    }
    if (IdleTimeoutSeconds <= 0.0f)
    {
        return ErrorResponse(TEXT("Idle timeout must be positive."));
    }
    if (!GEditor || !GEditor->Trans)
    {
        return ErrorResponse(TEXT("Unreal transaction buffer is unavailable."));
    }
    if (GEditor->Trans->IsActive())
    {
        return ErrorResponse(TEXT("Another Unreal transaction is already active."));
    }

    GActiveWorkflowTransaction =
        MakeUnique<FScopedTransaction>(FText::FromString(Description));
    if (!GActiveWorkflowTransaction->IsOutstanding())
    {
        GActiveWorkflowTransaction.Reset();
        return ErrorResponse(TEXT("Unreal could not begin the workflow transaction."));
    }
    GActiveWorkflowTransactionIndex = GEditor->Trans->GetQueueLength() - 1;
    GActiveWorkflowTransactionGuid =
        TransactionGuidAtIndex(GActiveWorkflowTransactionIndex);
    if (!GActiveWorkflowTransactionGuid.IsValid())
    {
        GActiveWorkflowTransaction->Cancel();
        GActiveWorkflowTransaction.Reset();
        GActiveWorkflowTransactionIndex = INDEX_NONE;
        return ErrorResponse(TEXT("Unreal did not create a workflow transaction record."));
    }
    GActiveWorkflowTransactionId = TransactionId;

    GWorkflowLease = MakeUnique<FWorkflowLease>();
    GWorkflowLease->TotalSteps = TotalSteps;
    GWorkflowLease->IdleTimeoutSeconds = IdleTimeoutSeconds;
    GWorkflowLease->LastHeartbeatSeconds = FPlatformTime::Seconds();
    GWorkflowLease->SlowTask = MakeUnique<FScopedSlowTask>(
        static_cast<float>(TotalSteps),
        FText::FromString(Description));
    if (bShowDialog && !FApp::IsUnattended())
    {
        GWorkflowLease->SlowTask->MakeDialog(true);
    }
    GWorkflowLease->TickerHandle =
        FTSTicker::GetCoreTicker().AddTicker(
            TEXT("UnrealMCP.WorkflowLease"),
            1.0f,
            [](float)
            {
                return TickWorkflowLease();
            });
    return TransactionResponse(
        TransactionId, GActiveWorkflowTransactionIndex, false, false);
}

FString UMCPythonHelper::HeartbeatWorkflowTransaction(
    const FString& TransactionId,
    int32 CompletedSteps,
    int32 TotalSteps,
    const FString& Message,
    bool bHasSuccessfulWrite)
{
    if (!GActiveWorkflowTransaction || !GWorkflowLease)
    {
        return ErrorResponse(TEXT("No workflow transaction lease is active."));
    }
    if (TransactionId != GActiveWorkflowTransactionId)
    {
        return ErrorResponse(
            TEXT("Transaction id does not match the active transaction."));
    }
    if (GWorkflowLease->Phase != EWorkflowLeasePhase::Idle)
    {
        return ErrorResponse(
            TEXT("Cannot heartbeat while an atomic workflow step is active."));
    }
    if (TotalSteps != GWorkflowLease->TotalSteps)
    {
        return ErrorResponse(
            TEXT("Heartbeat total does not match the active lease."));
    }
    if (CompletedSteps < GWorkflowLease->CompletedSteps ||
        CompletedSteps > TotalSteps)
    {
        return ErrorResponse(TEXT("Heartbeat progress is out of range."));
    }

    GWorkflowLease->bHasSuccessfulWrite |= bHasSuccessfulWrite;
    const double Now = FPlatformTime::Seconds();
    if (Now - GWorkflowLease->LastHeartbeatSeconds >
        GWorkflowLease->IdleTimeoutSeconds)
    {
        return RecoverExpiredWorkflowLease(false);
    }

    const int32 ProgressDelta =
        CompletedSteps - GWorkflowLease->CompletedSteps;
    if (GWorkflowLease->SlowTask)
    {
        if (ProgressDelta > 0)
        {
            GWorkflowLease->SlowTask->EnterProgressFrame(
                static_cast<float>(ProgressDelta),
                FText::FromString(Message));
        }
        else if (!Message.IsEmpty())
        {
            GWorkflowLease->SlowTask->FrameMessage =
                FText::FromString(Message);
        }
        GWorkflowLease->SlowTask->TickProgress();
    }
    GWorkflowLease->CompletedSteps = CompletedSteps;
    GWorkflowLease->LastHeartbeatSeconds = Now;
    return LeaseResponse(true);
}

FString UMCPythonHelper::BeginWorkflowAtomicStep(
    const FString& TransactionId)
{
    if (!GActiveWorkflowTransaction || !GWorkflowLease)
    {
        return ErrorResponse(TEXT("No workflow transaction lease is active."));
    }
    if (TransactionId != GActiveWorkflowTransactionId)
    {
        return ErrorResponse(
            TEXT("Transaction id does not match the active transaction."));
    }
    if (GWorkflowLease->Phase != EWorkflowLeasePhase::Idle)
    {
        return ErrorResponse(TEXT("A workflow atomic step is already active."));
    }
    GWorkflowLease->Phase = EWorkflowLeasePhase::Atomic;
    return LeaseResponse(true);
}

FString UMCPythonHelper::EndWorkflowAtomicStep(
    const FString& TransactionId)
{
    if (!GActiveWorkflowTransaction || !GWorkflowLease)
    {
        return ErrorResponse(TEXT("No workflow transaction lease is active."));
    }
    if (TransactionId != GActiveWorkflowTransactionId)
    {
        return ErrorResponse(
            TEXT("Transaction id does not match the active transaction."));
    }
    if (GWorkflowLease->Phase != EWorkflowLeasePhase::Atomic)
    {
        return ErrorResponse(TEXT("No workflow atomic step is active."));
    }
    GWorkflowLease->Phase = EWorkflowLeasePhase::Idle;
    GWorkflowLease->LastHeartbeatSeconds = FPlatformTime::Seconds();
    return LeaseResponse(true);
}

FString UMCPythonHelper::RequestWorkflowCancellation(
    const FString& TransactionId)
{
    if (!GActiveWorkflowTransaction || !GWorkflowLease)
    {
        return ErrorResponse(TEXT("No workflow transaction lease is active."));
    }
    if (TransactionId != GActiveWorkflowTransactionId)
    {
        return ErrorResponse(
            TEXT("Transaction id does not match the active transaction."));
    }
    GWorkflowLease->bCancelRequested = true;
    return LeaseResponse(true);
}

FString UMCPythonHelper::CommitWorkflowTransaction(const FString& TransactionId)
{
    if (!GActiveWorkflowTransaction)
    {
        return ErrorResponse(TEXT("No workflow transaction is active."));
    }
    if (TransactionId != GActiveWorkflowTransactionId)
    {
        return ErrorResponse(TEXT("Transaction id does not match the active transaction."));
    }
    const int32 TransactionIndex = GActiveWorkflowTransactionIndex;
    const FGuid TransactionGuid = GActiveWorkflowTransactionGuid;
    GActiveWorkflowTransaction.Reset();
    ClearActiveWorkflowIdentifiers();
    ClearWorkflowLease();
    const bool bTransactionRecorded =
        IsCurrentWorkflowTransaction(TransactionIndex, TransactionGuid);
    if (bTransactionRecorded)
    {
        GLastCommittedWorkflowTransactionId = TransactionId;
        GLastCommittedWorkflowTransactionIndex = TransactionIndex;
        GLastCommittedWorkflowTransactionGuid = TransactionGuid;
    }
    return TransactionResponse(
        TransactionId,
        TransactionIndex,
        false,
        false,
        bTransactionRecorded,
        bTransactionRecorded);
}

FString UMCPythonHelper::CancelWorkflowTransaction(const FString& TransactionId)
{
    if (!GActiveWorkflowTransaction)
    {
        return ErrorResponse(TEXT("No workflow transaction is active."));
    }
    if (TransactionId != GActiveWorkflowTransactionId)
    {
        return ErrorResponse(TEXT("Transaction id does not match the active transaction."));
    }
    const int32 TransactionIndex = GActiveWorkflowTransactionIndex;
    GActiveWorkflowTransaction->Cancel();
    GActiveWorkflowTransaction.Reset();
    ClearActiveWorkflowIdentifiers();
    ClearWorkflowLease();
    return TransactionResponse(
        TransactionId, TransactionIndex, false, false, false, false);
}

FString UMCPythonHelper::RollbackWorkflowTransaction(const FString& TransactionId)
{
    if (!GActiveWorkflowTransaction)
    {
        return ErrorResponse(TEXT("No workflow transaction is active."));
    }
    if (TransactionId != GActiveWorkflowTransactionId)
    {
        return ErrorResponse(TEXT("Transaction id does not match the active transaction."));
    }
    const int32 TransactionIndex = GActiveWorkflowTransactionIndex;
    const FGuid TransactionGuid = GActiveWorkflowTransactionGuid;
    GActiveWorkflowTransaction.Reset();
    ClearActiveWorkflowIdentifiers();
    ClearWorkflowLease();
    const bool bTransactionRecorded =
        IsCurrentWorkflowTransaction(TransactionIndex, TransactionGuid);
    const bool bUndoSucceeded =
        bTransactionRecorded &&
        GEditor->UndoTransaction();
    return TransactionResponse(
        TransactionId,
        TransactionIndex,
        true,
        bUndoSucceeded,
        bTransactionRecorded,
        false);
}

FString UMCPythonHelper::UndoWorkflowTransaction(const FString& TransactionId)
{
    if (GActiveWorkflowTransaction)
    {
        return ErrorResponse(TEXT("Cannot undo while a workflow transaction is active."));
    }
    if (TransactionId.IsEmpty() || TransactionId != GLastCommittedWorkflowTransactionId)
    {
        return ErrorResponse(TEXT("Transaction id does not match the last committed transaction."));
    }
    const int32 TransactionIndex = GLastCommittedWorkflowTransactionIndex;
    const bool bTransactionRecorded =
        IsCurrentWorkflowTransaction(
            TransactionIndex, GLastCommittedWorkflowTransactionGuid);
    const bool bUndoSucceeded =
        bTransactionRecorded &&
        GEditor->UndoTransaction();
    if (bUndoSucceeded)
    {
        GLastCommittedWorkflowTransactionId.Empty();
        GLastCommittedWorkflowTransactionIndex = INDEX_NONE;
        GLastCommittedWorkflowTransactionGuid.Invalidate();
    }
    return TransactionResponse(
        TransactionId,
        TransactionIndex,
        true,
        bUndoSucceeded,
        bTransactionRecorded,
        false);
}
