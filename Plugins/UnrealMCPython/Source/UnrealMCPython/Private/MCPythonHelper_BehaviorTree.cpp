// Copyright (c) 2025 GenOrca (by zenoengine). All Rights Reserved.
// Behavior Tree authoring helpers — split out of MCPythonHelper.cpp.

#include "MCPythonHelper.h"
#include "Engine/SCS_Node.h"
#include "Engine/SimpleConstructionScript.h"
#include "WidgetBlueprint.h"
#include "Blueprint/WidgetTree.h"
#include "Components/Widget.h"
#include "Components/PanelWidget.h"
#include "Editor.h"
#include "Subsystems/AssetEditorSubsystem.h"
#include "Toolkits/AssetEditorToolkit.h"
#include "BlueprintEditor.h"
#include "BehaviorTree/BehaviorTree.h"
#include "BehaviorTree/BlackboardData.h"
#include "BehaviorTree/BTCompositeNode.h"
#include "BehaviorTree/BTTaskNode.h"
#include "BehaviorTree/BTDecorator.h"
#include "BehaviorTree/BTService.h"
#include "BehaviorTreeEditor.h"
#include "BehaviorTreeGraphNode.h"
#include "BehaviorTreeGraph.h"
#include "BehaviorTreeGraphNode_Root.h"
#include "BehaviorTreeGraphNode_Composite.h"
#include "BehaviorTreeGraphNode_Task.h"
#include "BehaviorTreeGraphNode_Decorator.h"
#include "BehaviorTreeGraphNode_Service.h"
#include "BehaviorTreeGraphNode_SimpleParallel.h"
#include "BehaviorTreeGraphNode_SubtreeTask.h"
#include "EdGraphSchema_BehaviorTree.h"
#include "EdGraph/EdGraph.h"
#include "UObject/UObjectIterator.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/SkeletalMeshSocket.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Serialization/JsonWriter.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonReader.h"
// Blueprint graph includes
#include "K2Node_Event.h"
#include "K2Node_ComponentBoundEvent.h"
#include "K2Node_CustomEvent.h"
#include "K2Node_CallFunction.h"
#include "K2Node_IfThenElse.h"
#include "K2Node_ExecutionSequence.h"
#include "K2Node_VariableGet.h"
#include "K2Node_VariableSet.h"
#include "K2Node_MacroInstance.h"
#include "K2Node_DynamicCast.h"
#include "K2Node_InputKey.h"
#include "K2Node_SpawnActorFromClass.h"
#include "EdGraphSchema_K2.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Engine/Blueprint.h"
#include "UObject/UnrealType.h"
#include "UObject/TextProperty.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/TextBlock.h"
// AnimGraph authoring (editor-only AnimGraph module)
#include "Animation/AnimBlueprint.h"
#include "Animation/AnimSequence.h"
#include "AnimGraphNode_StateMachine.h"
#include "AnimGraphNode_SequencePlayer.h"
#include "AnimGraphNode_Root.h"
#include "AnimGraphNode_StateResult.h"
#include "AnimGraphNode_TransitionResult.h"
#include "AnimStateNode.h"
#include "AnimStateTransitionNode.h"
#include "AnimStateEntryNode.h"
#include "AnimationStateMachineGraph.h"
#include "Kismet/KismetMathLibrary.h"
// Editor viewport projection
#include "LevelEditorViewport.h"
#include "EditorViewportClient.h"
#include "SceneView.h"
#include "MCPythonHelperInternal.h"

// ─── Behavior Tree Helpers (internal) ────────────────────────────────────────

static FMCPythonBTNodeInfo SerializeBTNode(UBTCompositeNode* Node)
{
    FMCPythonBTNodeInfo Info;
    if (!Node) return Info;

    Info.NodeName = Node->GetNodeName();
    Info.NodeClass = Node->GetClass()->GetName();

    // Services on this composite node
    for (UBTService* Svc : Node->Services)
    {
        if (Svc)
        {
            Info.ServiceClasses.Add(Svc->GetClass()->GetName());
            Info.ServiceNames.Add(Svc->GetNodeName());
        }
    }

    // Children
    for (const FBTCompositeChild& Child : Node->Children)
    {
        if (Child.ChildComposite)
        {
            FMCPythonBTNodeInfo ChildInfo = SerializeBTNode(Child.ChildComposite);
            // Decorators are stored per-child-connection
            for (UBTDecorator* Dec : Child.Decorators)
            {
                if (Dec)
                {
                    ChildInfo.DecoratorClasses.Add(Dec->GetClass()->GetName());
                    ChildInfo.DecoratorNames.Add(Dec->GetNodeName());
                }
            }
            Info.Children.Add(ChildInfo);
        }
        else if (Child.ChildTask)
        {
            FMCPythonBTNodeInfo TaskInfo;
            TaskInfo.NodeName = Child.ChildTask->GetNodeName();
            TaskInfo.NodeClass = Child.ChildTask->GetClass()->GetName();

            // Decorators on this child connection
            for (UBTDecorator* Dec : Child.Decorators)
            {
                if (Dec)
                {
                    TaskInfo.DecoratorClasses.Add(Dec->GetClass()->GetName());
                    TaskInfo.DecoratorNames.Add(Dec->GetNodeName());
                }
            }

            // Services on task node
            for (UBTService* Svc : Child.ChildTask->Services)
            {
                if (Svc)
                {
                    TaskInfo.ServiceClasses.Add(Svc->GetClass()->GetName());
                    TaskInfo.ServiceNames.Add(Svc->GetNodeName());
                }
            }

            Info.Children.Add(TaskInfo);
        }
    }

    return Info;
}

static UBTNode* FindNodeByName(UBTCompositeNode* Root, const FString& Name)
{
    if (!Root) return nullptr;

    // Check root itself
    if (Root->GetNodeName() == Name || Root->GetName() == Name)
        return Root;

    // Check root's services
    for (UBTService* Svc : Root->Services)
    {
        if (Svc && (Svc->GetNodeName() == Name || Svc->GetName() == Name))
            return Svc;
    }

    // Check children
    for (const FBTCompositeChild& Child : Root->Children)
    {
        // Check decorators on this child
        for (UBTDecorator* Dec : Child.Decorators)
        {
            if (Dec && (Dec->GetNodeName() == Name || Dec->GetName() == Name))
                return Dec;
        }

        if (Child.ChildComposite)
        {
            UBTNode* Found = FindNodeByName(Child.ChildComposite, Name);
            if (Found) return Found;
        }
        else if (Child.ChildTask)
        {
            if (Child.ChildTask->GetNodeName() == Name || Child.ChildTask->GetName() == Name)
                return Child.ChildTask;

            // Check task's services
            for (UBTService* Svc : Child.ChildTask->Services)
            {
                if (Svc && (Svc->GetNodeName() == Name || Svc->GetName() == Name))
                    return Svc;
            }
        }
    }

    return nullptr;
}

// ─── JSON serialization for BT tree ─────────────────────────────────────────

static TSharedPtr<FJsonObject> BTNodeInfoToJson(const FMCPythonBTNodeInfo& Info)
{
    TSharedPtr<FJsonObject> Obj = MakeShareable(new FJsonObject());
    Obj->SetStringField(TEXT("node_name"), Info.NodeName);
    Obj->SetStringField(TEXT("node_class"), Info.NodeClass);

    if (Info.DecoratorClasses.Num() > 0)
    {
        TArray<TSharedPtr<FJsonValue>> DecArr;
        for (int32 i = 0; i < Info.DecoratorClasses.Num(); ++i)
        {
            TSharedPtr<FJsonObject> DecObj = MakeShareable(new FJsonObject());
            DecObj->SetStringField(TEXT("class"), Info.DecoratorClasses[i]);
            if (Info.DecoratorNames.IsValidIndex(i))
                DecObj->SetStringField(TEXT("name"), Info.DecoratorNames[i]);
            DecArr.Add(MakeShareable(new FJsonValueObject(DecObj)));
        }
        Obj->SetArrayField(TEXT("decorators"), DecArr);
    }

    if (Info.ServiceClasses.Num() > 0)
    {
        TArray<TSharedPtr<FJsonValue>> SvcArr;
        for (int32 i = 0; i < Info.ServiceClasses.Num(); ++i)
        {
            TSharedPtr<FJsonObject> SvcObj = MakeShareable(new FJsonObject());
            SvcObj->SetStringField(TEXT("class"), Info.ServiceClasses[i]);
            if (Info.ServiceNames.IsValidIndex(i))
                SvcObj->SetStringField(TEXT("name"), Info.ServiceNames[i]);
            SvcArr.Add(MakeShareable(new FJsonValueObject(SvcObj)));
        }
        Obj->SetArrayField(TEXT("services"), SvcArr);
    }

    if (Info.Children.Num() > 0)
    {
        TArray<TSharedPtr<FJsonValue>> ChildArr;
        for (const FMCPythonBTNodeInfo& Child : Info.Children)
        {
            ChildArr.Add(MakeShareable(new FJsonValueObject(BTNodeInfoToJson(Child))));
        }
        Obj->SetArrayField(TEXT("children"), ChildArr);
    }

    return Obj;
}

// ─── Behavior Tree UFUNCTION Implementations ────────────────────────────────

FString UMCPythonHelper::GetBehaviorTreeStructure(UBehaviorTree* BehaviorTree)
{
    if (!BehaviorTree || !BehaviorTree->RootNode)
    {
        return TEXT("{\"success\":false,\"message\":\"Invalid BehaviorTree or empty tree.\"}");
    }

    FMCPythonBTNodeInfo RootInfo = SerializeBTNode(BehaviorTree->RootNode);
    TSharedPtr<FJsonObject> ResultObj = MakeShareable(new FJsonObject());
    ResultObj->SetBoolField(TEXT("success"), true);
    ResultObj->SetObjectField(TEXT("root"), BTNodeInfoToJson(RootInfo));

    FString OutputString;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&OutputString);
    FJsonSerializer::Serialize(ResultObj.ToSharedRef(), Writer);
    return OutputString;
}

bool UMCPythonHelper::SetBehaviorTreeBlackboard(UBehaviorTree* BehaviorTree, UBlackboardData* BlackboardData)
{
    if (!BehaviorTree) return false;

    BehaviorTree->BlackboardAsset = BlackboardData;
    BehaviorTree->MarkPackageDirty();
    return true;
}

FString UMCPythonHelper::GetBehaviorTreeNodeDetails(UBehaviorTree* BehaviorTree, const FString& NodeName)
{
    if (!BehaviorTree || !BehaviorTree->RootNode)
    {
        return TEXT("{\"success\":false,\"message\":\"Invalid BehaviorTree or empty tree.\"}");
    }

    UBTNode* FoundNode = FindNodeByName(BehaviorTree->RootNode, NodeName);
    if (!FoundNode)
    {
        TSharedPtr<FJsonObject> ErrObj = MakeShareable(new FJsonObject());
        ErrObj->SetBoolField(TEXT("success"), false);
        ErrObj->SetStringField(TEXT("message"), FString::Printf(TEXT("Node '%s' not found in behavior tree."), *NodeName));
        FString ErrStr;
        auto ErrWriter = TJsonWriterFactory<>::Create(&ErrStr);
        FJsonSerializer::Serialize(ErrObj.ToSharedRef(), ErrWriter);
        return ErrStr;
    }

    TSharedPtr<FJsonObject> JsonObj = MakeShareable(new FJsonObject());
    JsonObj->SetBoolField(TEXT("success"), true);
    JsonObj->SetStringField(TEXT("node_name"), FoundNode->GetNodeName());
    JsonObj->SetStringField(TEXT("node_class"), FoundNode->GetClass()->GetName());

    // Serialize EditAnywhere properties
    TSharedPtr<FJsonObject> PropsObj = MakeShareable(new FJsonObject());
    for (TFieldIterator<FProperty> PropIt(FoundNode->GetClass()); PropIt; ++PropIt)
    {
        FProperty* Prop = *PropIt;
        if (!Prop->HasAnyPropertyFlags(CPF_Edit)) continue;

        FString ValueStr;
        const void* ValueAddr = Prop->ContainerPtrToValuePtr<void>(FoundNode);
        Prop->ExportText_Direct(ValueStr, ValueAddr, nullptr, FoundNode, PPF_None);
        PropsObj->SetStringField(Prop->GetName(), ValueStr);
    }
    JsonObj->SetObjectField(TEXT("properties"), PropsObj);

    // If composite node, include services and child count
    UBTCompositeNode* CompNode = Cast<UBTCompositeNode>(FoundNode);
    if (CompNode)
    {
        JsonObj->SetNumberField(TEXT("child_count"), CompNode->Children.Num());

        TArray<TSharedPtr<FJsonValue>> ServicesArr;
        for (UBTService* Svc : CompNode->Services)
        {
            if (Svc)
            {
                TSharedPtr<FJsonObject> SvcObj = MakeShareable(new FJsonObject());
                SvcObj->SetStringField(TEXT("name"), Svc->GetNodeName());
                SvcObj->SetStringField(TEXT("class"), Svc->GetClass()->GetName());
                ServicesArr.Add(MakeShareable(new FJsonValueObject(SvcObj)));
            }
        }
        if (ServicesArr.Num() > 0)
        {
            JsonObj->SetArrayField(TEXT("services"), ServicesArr);
        }
    }

    FString OutputString;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&OutputString);
    FJsonSerializer::Serialize(JsonObj.ToSharedRef(), Writer);
    return OutputString;
}

FString UMCPythonHelper::GetSelectedBTNodes()
{
    if (!GEditor)
    {
        return TEXT("{\"success\":false,\"message\":\"GEditor is null.\"}");
    }

    auto* Subsystem = GEditor->GetEditorSubsystem<UAssetEditorSubsystem>();
    if (!Subsystem)
    {
        return TEXT("{\"success\":false,\"message\":\"AssetEditorSubsystem not available.\"}");
    }

    for (UObject* Asset : Subsystem->GetAllEditedAssets())
    {
        UBehaviorTree* BT = Cast<UBehaviorTree>(Asset);
        if (!BT) continue;

        IAssetEditorInstance* EditorInstance = Subsystem->FindEditorForAsset(Asset, false);
        FAssetEditorToolkit* EditorToolkit = static_cast<FAssetEditorToolkit*>(EditorInstance);
        if (!EditorToolkit) continue;

        TSharedPtr<SDockTab> Tab = EditorToolkit->GetTabManager()->GetOwnerTab();
        if (!Tab.IsValid() || !Tab->IsForeground()) continue;

        FBehaviorTreeEditor* BTEditor = static_cast<FBehaviorTreeEditor*>(EditorToolkit);
        if (!BTEditor) continue;

        FGraphPanelSelectionSet SelectedNodes = BTEditor->GetSelectedNodes();

        TArray<TSharedPtr<FJsonValue>> NodesArr;
        for (UObject* NodeObj : SelectedNodes)
        {
            UBehaviorTreeGraphNode* GraphNode = Cast<UBehaviorTreeGraphNode>(NodeObj);
            if (!GraphNode) continue;

            UBTNode* BTNode = Cast<UBTNode>(GraphNode->NodeInstance);
            if (!BTNode) continue;

            TSharedPtr<FJsonObject> NodeJson = MakeShareable(new FJsonObject());
            NodeJson->SetStringField(TEXT("node_name"), BTNode->GetNodeName());
            NodeJson->SetStringField(TEXT("node_class"), BTNode->GetClass()->GetName());

            // Classify node type
            FString NodeType;
            if (Cast<UBTCompositeNode>(BTNode))
                NodeType = TEXT("composite");
            else if (Cast<UBTTaskNode>(BTNode))
                NodeType = TEXT("task");
            else if (Cast<UBTDecorator>(BTNode))
                NodeType = TEXT("decorator");
            else if (Cast<UBTService>(BTNode))
                NodeType = TEXT("service");
            else
                NodeType = TEXT("unknown");
            NodeJson->SetStringField(TEXT("node_type"), NodeType);

            // Serialize EditAnywhere properties
            TSharedPtr<FJsonObject> PropsObj = MakeShareable(new FJsonObject());
            for (TFieldIterator<FProperty> PropIt(BTNode->GetClass()); PropIt; ++PropIt)
            {
                FProperty* Prop = *PropIt;
                if (!Prop->HasAnyPropertyFlags(CPF_Edit)) continue;

                FString ValueStr;
                const void* ValueAddr = Prop->ContainerPtrToValuePtr<void>(BTNode);
                Prop->ExportText_Direct(ValueStr, ValueAddr, nullptr, BTNode, PPF_None);
                PropsObj->SetStringField(Prop->GetName(), ValueStr);
            }
            NodeJson->SetObjectField(TEXT("properties"), PropsObj);

            NodesArr.Add(MakeShareable(new FJsonValueObject(NodeJson)));
        }

        // Build result
        TSharedPtr<FJsonObject> ResultObj = MakeShareable(new FJsonObject());
        ResultObj->SetBoolField(TEXT("success"), true);
        ResultObj->SetStringField(TEXT("behavior_tree_path"), BT->GetPathName());
        ResultObj->SetArrayField(TEXT("selected_nodes"), NodesArr);
        ResultObj->SetNumberField(TEXT("count"), NodesArr.Num());

        FString ResultStr;
        TSharedRef<TJsonWriter<>> ResultWriter = TJsonWriterFactory<>::Create(&ResultStr);
        FJsonSerializer::Serialize(ResultObj.ToSharedRef(), ResultWriter);
        return ResultStr;
    }

    return TEXT("{\"success\":false,\"message\":\"No Behavior Tree editor is open in the foreground.\"}");
}

// ─── Build BT Helpers ────────────────────────────────────────────────────────

static UClass* FindBTNodeClass(const FString& ClassName)
{
    for (TObjectIterator<UClass> It; It; ++It)
    {
        UClass* Cls = *It;
        if (Cls->GetName() == ClassName &&
            Cls->IsChildOf(UBTNode::StaticClass()) &&
            !Cls->HasAnyClassFlags(CLASS_Abstract))
        {
            return Cls;
        }
    }
    return nullptr;
}

static void SetBTNodeProperties(UBTNode* Node, const TSharedPtr<FJsonObject>& PropertiesObj)
{
    if (!Node || !PropertiesObj.IsValid()) return;

    for (auto& Pair : PropertiesObj->Values)
    {
        FProperty* Prop = Node->GetClass()->FindPropertyByName(FName(*Pair.Key));
        if (!Prop) continue;

        FString ValueStr;
        if (Pair.Value->TryGetString(ValueStr))
        {
            // Already a string — use as-is
        }
        else if (Pair.Value->Type == EJson::Number)
        {
            ValueStr = FString::SanitizeFloat(Pair.Value->AsNumber());
        }
        else if (Pair.Value->Type == EJson::Boolean)
        {
            ValueStr = Pair.Value->AsBool() ? TEXT("true") : TEXT("false");
        }
        else
        {
            continue;
        }

        void* ValueAddr = Prop->ContainerPtrToValuePtr<void>(Node);

        FStructProperty* StructProp = CastField<FStructProperty>(Prop);
        if (StructProp && StructProp->Struct->FindPropertyByName(TEXT("DefaultValue")))
        {
            FString WrappedValue = FString::Printf(TEXT("(DefaultValue=%s)"), *ValueStr);
            Prop->ImportText_Direct(*WrappedValue, ValueAddr, Node, PPF_None);
        }
        else
        {
            Prop->ImportText_Direct(*ValueStr, ValueAddr, Node, PPF_None);
        }
    }
}

static UEdGraphPin* FindGraphPin(UEdGraphNode* Node, EEdGraphPinDirection Direction)
{
    for (UEdGraphPin* Pin : Node->Pins)
    {
        if (Pin->Direction == Direction)
            return Pin;
    }
    return nullptr;
}

static int32 CountSubtreeLeaves(UEdGraphNode* Node)
{
    int32 Total = 0;
    for (UEdGraphPin* Pin : Node->Pins)
    {
        if (Pin->Direction == EGPD_Output)
        {
            for (UEdGraphPin* LinkedPin : Pin->LinkedTo)
            {
                Total += CountSubtreeLeaves(LinkedPin->GetOwningNode());
            }
        }
    }
    return FMath::Max(1, Total);
}

static void LayoutBTGraphNodes(UEdGraphNode* Node, float LeftX, float Width, float Y)
{
    const float NodeWidth = 280.0f;
    const float YStep = 200.0f;

    Node->NodePosX = (int32)(LeftX + Width / 2.0f - NodeWidth / 2.0f);
    Node->NodePosY = (int32)Y;

    float SubNodeHeight = 0.0f;
    UBehaviorTreeGraphNode* BTNode = Cast<UBehaviorTreeGraphNode>(Node);
    if (BTNode)
    {
        SubNodeHeight = (BTNode->Decorators.Num() + BTNode->Services.Num()) * 60.0f;
    }

    float ChildY = Y + YStep + SubNodeHeight;
    float ChildX = LeftX;

    for (UEdGraphPin* Pin : Node->Pins)
    {
        if (Pin->Direction == EGPD_Output)
        {
            for (UEdGraphPin* LinkedPin : Pin->LinkedTo)
            {
                UEdGraphNode* Child = LinkedPin->GetOwningNode();
                int32 ChildLeaves = CountSubtreeLeaves(Child);
                float ChildWidth = ChildLeaves * (NodeWidth + 40.0f);
                LayoutBTGraphNodes(Child, ChildX, ChildWidth, ChildY);
                ChildX += ChildWidth;
            }
        }
    }
}

static bool CheckClassAncestor(UClass* NodeClass, const TCHAR* AncestorName)
{
    for (UClass* C = NodeClass; C; C = C->GetSuperClass())
    {
        if (C->GetName() == AncestorName)
            return true;
    }
    return false;
}

static UBehaviorTreeGraphNode* CreateBTGraphNodeRecursive(
    UBehaviorTreeGraph* Graph,
    UBehaviorTree* BT,
    const TSharedPtr<FJsonObject>& JsonNode)
{
    if (!JsonNode.IsValid() || !JsonNode->HasField(TEXT("node_class")))
        return nullptr;

    FString NodeClassName = JsonNode->GetStringField(TEXT("node_class"));
    UClass* NodeClass = FindBTNodeClass(NodeClassName);
    if (!NodeClass)
    {
        UE_LOG(LogTemp, Warning, TEXT("BuildBT: Class '%s' not found"), *NodeClassName);
        return nullptr;
    }

    // Create runtime node
    UBTNode* RuntimeNode = NewObject<UBTNode>(BT, NodeClass);

    // Classify node type
    bool bIsComposite = NodeClass->IsChildOf(UBTCompositeNode::StaticClass());
    bool bIsTask = NodeClass->IsChildOf(UBTTaskNode::StaticClass());
    bool bIsSimpleParallel = CheckClassAncestor(NodeClass, TEXT("BTComposite_SimpleParallel"));
    bool bIsSubtreeTask = CheckClassAncestor(NodeClass, TEXT("BTTask_RunBehavior"))
                       || CheckClassAncestor(NodeClass, TEXT("BTTask_RunBehaviorDynamic"));

    // Create appropriate graph node
    UBehaviorTreeGraphNode* GraphNode = nullptr;

    if (bIsSimpleParallel)
    {
        FGraphNodeCreator<UBehaviorTreeGraphNode_SimpleParallel> Creator(*Graph);
        GraphNode = Creator.CreateNode(false);
        Creator.Finalize();
    }
    else if (bIsComposite)
    {
        FGraphNodeCreator<UBehaviorTreeGraphNode_Composite> Creator(*Graph);
        GraphNode = Creator.CreateNode(false);
        Creator.Finalize();
    }
    else if (bIsSubtreeTask)
    {
        FGraphNodeCreator<UBehaviorTreeGraphNode_SubtreeTask> Creator(*Graph);
        GraphNode = Creator.CreateNode(false);
        Creator.Finalize();
    }
    else if (bIsTask)
    {
        FGraphNodeCreator<UBehaviorTreeGraphNode_Task> Creator(*Graph);
        GraphNode = Creator.CreateNode(false);
        Creator.Finalize();
    }
    else
    {
        UE_LOG(LogTemp, Warning, TEXT("BuildBT: Unsupported node type for '%s'"), *NodeClassName);
        return nullptr;
    }

    // Set NodeInstance
    GraphNode->NodeInstance = RuntimeNode;

    // Set properties on the runtime node
    if (JsonNode->HasField(TEXT("properties")))
    {
        const TSharedPtr<FJsonObject>& PropsObj = JsonNode->GetObjectField(TEXT("properties"));
        SetBTNodeProperties(RuntimeNode, PropsObj);
    }

    // Add decorators as sub-nodes
    if (JsonNode->HasField(TEXT("decorators")))
    {
        const TArray<TSharedPtr<FJsonValue>>& DecoratorsArr = JsonNode->GetArrayField(TEXT("decorators"));
        for (const auto& DecVal : DecoratorsArr)
        {
            const TSharedPtr<FJsonObject>& DecObj = DecVal->AsObject();
            if (!DecObj.IsValid() || !DecObj->HasField(TEXT("class"))) continue;

            FString DecClassName = DecObj->GetStringField(TEXT("class"));
            UClass* DecClass = FindBTNodeClass(DecClassName);
            if (!DecClass || !DecClass->IsChildOf(UBTDecorator::StaticClass()))
            {
                UE_LOG(LogTemp, Warning, TEXT("BuildBT: Decorator class '%s' not found or invalid"), *DecClassName);
                continue;
            }

            UBTDecorator* DecRuntime = NewObject<UBTDecorator>(BT, DecClass);
            if (DecObj->HasField(TEXT("properties")))
            {
                SetBTNodeProperties(DecRuntime, DecObj->GetObjectField(TEXT("properties")));
            }

            UBehaviorTreeGraphNode_Decorator* DecGraphNode =
                NewObject<UBehaviorTreeGraphNode_Decorator>(Graph);
            DecGraphNode->NodeInstance = DecRuntime;
            GraphNode->AddSubNode(DecGraphNode, Graph);
        }
    }

    // Add services as sub-nodes
    if (JsonNode->HasField(TEXT("services")))
    {
        const TArray<TSharedPtr<FJsonValue>>& ServicesArr = JsonNode->GetArrayField(TEXT("services"));
        for (const auto& SvcVal : ServicesArr)
        {
            const TSharedPtr<FJsonObject>& SvcObj = SvcVal->AsObject();
            if (!SvcObj.IsValid() || !SvcObj->HasField(TEXT("class"))) continue;

            FString SvcClassName = SvcObj->GetStringField(TEXT("class"));
            UClass* SvcClass = FindBTNodeClass(SvcClassName);
            if (!SvcClass || !SvcClass->IsChildOf(UBTService::StaticClass()))
            {
                UE_LOG(LogTemp, Warning, TEXT("BuildBT: Service class '%s' not found or invalid"), *SvcClassName);
                continue;
            }

            UBTService* SvcRuntime = NewObject<UBTService>(BT, SvcClass);
            if (SvcObj->HasField(TEXT("properties")))
            {
                SetBTNodeProperties(SvcRuntime, SvcObj->GetObjectField(TEXT("properties")));
            }

            UBehaviorTreeGraphNode_Service* SvcGraphNode =
                NewObject<UBehaviorTreeGraphNode_Service>(Graph);
            SvcGraphNode->NodeInstance = SvcRuntime;
            GraphNode->AddSubNode(SvcGraphNode, Graph);
        }
    }

    // Recurse for children (only composites have children)
    if (bIsComposite && JsonNode->HasField(TEXT("children")))
    {
        const TArray<TSharedPtr<FJsonValue>>& ChildrenArr = JsonNode->GetArrayField(TEXT("children"));
        UEdGraphPin* OutputPin = FindGraphPin(GraphNode, EGPD_Output);

        if (OutputPin)
        {
            for (const auto& ChildVal : ChildrenArr)
            {
                const TSharedPtr<FJsonObject>& ChildObj = ChildVal->AsObject();
                if (!ChildObj.IsValid()) continue;

                UBehaviorTreeGraphNode* ChildGraphNode =
                    CreateBTGraphNodeRecursive(Graph, BT, ChildObj);

                if (ChildGraphNode)
                {
                    UEdGraphPin* ChildInputPin = FindGraphPin(ChildGraphNode, EGPD_Input);
                    if (ChildInputPin)
                    {
                        OutputPin->MakeLinkTo(ChildInputPin);
                    }
                }
            }
        }
    }

    return GraphNode;
}

// ─── BuildBehaviorTree UFUNCTION ─────────────────────────────────────────────

FString UMCPythonHelper::BuildBehaviorTree(UBehaviorTree* BehaviorTree, const FString& TreeStructureJson)
{
    if (!BehaviorTree)
    {
        return TEXT("{\"success\":false,\"message\":\"Invalid BehaviorTree asset.\"}");
    }

    // Parse JSON
    TSharedPtr<FJsonObject> JsonObj;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(TreeStructureJson);
    if (!FJsonSerializer::Deserialize(Reader, JsonObj) || !JsonObj.IsValid())
    {
        return TEXT("{\"success\":false,\"message\":\"Failed to parse JSON input.\"}");
    }

    // Get BT graph — create if missing (e.g. asset created without factory)
    UBehaviorTreeGraph* BTGraph = Cast<UBehaviorTreeGraph>(BehaviorTree->BTGraph);
    if (!BTGraph)
    {
        UBehaviorTreeGraph* NewGraph = NewObject<UBehaviorTreeGraph>(BehaviorTree, NAME_None, RF_Transactional);
        NewGraph->Schema = UEdGraphSchema_BehaviorTree::StaticClass();
        BehaviorTree->BTGraph = NewGraph;

        const UEdGraphSchema* Schema = NewGraph->GetSchema();
        if (Schema)
        {
            Schema->CreateDefaultNodesForGraph(*NewGraph);
        }

        BTGraph = NewGraph;
    }

    // Find root graph node
    UBehaviorTreeGraphNode_Root* RootGraphNode = nullptr;
    for (UEdGraphNode* Node : BTGraph->Nodes)
    {
        RootGraphNode = Cast<UBehaviorTreeGraphNode_Root>(Node);
        if (RootGraphNode) break;
    }

    if (!RootGraphNode)
    {
        return TEXT("{\"success\":false,\"message\":\"No root node found in BT graph.\"}");
    }

    // Remove all existing non-root graph nodes
    TArray<UEdGraphNode*> NodesToRemove;
    for (UEdGraphNode* Node : BTGraph->Nodes)
    {
        if (Node != RootGraphNode)
        {
            NodesToRemove.Add(Node);
        }
    }
    for (UEdGraphNode* Node : NodesToRemove)
    {
        BTGraph->RemoveNode(Node);
    }

    // Clear root pin links and sub-nodes
    for (UEdGraphPin* Pin : RootGraphNode->Pins)
    {
        Pin->BreakAllPinLinks();
    }
    RootGraphNode->Decorators.Empty();
    RootGraphNode->Services.Empty();

    // Create graph nodes from JSON
    UBehaviorTreeGraphNode* FirstChild = CreateBTGraphNodeRecursive(BTGraph, BehaviorTree, JsonObj);

    if (!FirstChild)
    {
        return TEXT("{\"success\":false,\"message\":\"Failed to create root node from JSON. Check node_class names.\"}");
    }

    // Connect root to first child
    UEdGraphPin* RootOutput = FindGraphPin(RootGraphNode, EGPD_Output);
    UEdGraphPin* ChildInput = FindGraphPin(FirstChild, EGPD_Input);
    if (RootOutput && ChildInput)
    {
        RootOutput->MakeLinkTo(ChildInput);
    }

    // Layout nodes BEFORE UpdateAsset — RebuildChildOrder sorts children by NodePosX
    float TotalWidth = CountSubtreeLeaves(RootGraphNode) * 320.0f;
    LayoutBTGraphNodes(RootGraphNode, 0.0f, TotalWidth, 0.0f);

    // Compile graph → runtime tree (uses node positions for child ordering)
    BTGraph->UpdateAsset();

    BehaviorTree->MarkPackageDirty();

    // Return success
    TSharedPtr<FJsonObject> ResultObj = MakeShareable(new FJsonObject());
    ResultObj->SetBoolField(TEXT("success"), true);
    ResultObj->SetStringField(TEXT("message"), TEXT("Behavior tree built successfully from JSON."));

    FString ResultStr;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&ResultStr);
    FJsonSerializer::Serialize(ResultObj.ToSharedRef(), Writer);
    return ResultStr;
}

// ─── ListBTNodeClasses UFUNCTION ─────────────────────────────────────────────

FString UMCPythonHelper::ListBTNodeClasses()
{
    TArray<TSharedPtr<FJsonValue>> Composites, Tasks, Decorators, Services;

    for (TObjectIterator<UClass> It; It; ++It)
    {
        UClass* Cls = *It;
        if (Cls->HasAnyClassFlags(CLASS_Abstract | CLASS_Deprecated | CLASS_NewerVersionExists))
            continue;

        FString ClassName = Cls->GetName();
        TSharedPtr<FJsonValue> NameVal = MakeShareable(new FJsonValueString(ClassName));

        if (Cls->IsChildOf(UBTCompositeNode::StaticClass()))
            Composites.Add(NameVal);
        else if (Cls->IsChildOf(UBTTaskNode::StaticClass()))
            Tasks.Add(NameVal);
        else if (Cls->IsChildOf(UBTDecorator::StaticClass()))
            Decorators.Add(NameVal);
        else if (Cls->IsChildOf(UBTService::StaticClass()))
            Services.Add(NameVal);
    }

    TSharedPtr<FJsonObject> Result = MakeShareable(new FJsonObject());
    Result->SetBoolField(TEXT("success"), true);
    Result->SetArrayField(TEXT("composites"), Composites);
    Result->SetArrayField(TEXT("tasks"), Tasks);
    Result->SetArrayField(TEXT("decorators"), Decorators);
    Result->SetArrayField(TEXT("services"), Services);

    FString OutputString;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&OutputString);
    FJsonSerializer::Serialize(Result.ToSharedRef(), Writer);
    return OutputString;
}
