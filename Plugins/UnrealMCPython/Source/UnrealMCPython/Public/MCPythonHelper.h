// Copyright (c) 2025 GenOrca (by zenoengine). All Rights Reserved.

#pragma once

#include "Kismet/BlueprintFunctionLibrary.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
#include "BehaviorTree/BehaviorTree.h"
#include "BehaviorTree/BlackboardData.h"
#include "Components/Widget.h"
#include "MCPythonHelper.generated.h"


USTRUCT(BlueprintType)
struct FMCPythonPinLinkInfo
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString NodeName;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString NodeTitle;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString PinName;
};

USTRUCT(BlueprintType)
struct FMCPythonBlueprintPinInfo
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString PinName;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString FriendlyName;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString Direction;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString PinType;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString PinSubType;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString DefaultValue;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    TArray<FMCPythonPinLinkInfo> LinkedTo;
};

USTRUCT(BlueprintType)
struct FMCPythonBlueprintNodeInfo
{
    GENERATED_BODY()
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString NodeName;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString NodeTitle;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString NodeComment;
    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    TArray<FMCPythonBlueprintPinInfo> Pins;
};

USTRUCT(BlueprintType)
struct FMCPythonBTNodeInfo
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString NodeName;

    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    FString NodeClass;

    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    TArray<FString> DecoratorClasses;

    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    TArray<FString> DecoratorNames;

    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    TArray<FString> ServiceClasses;

    UPROPERTY(BlueprintReadOnly, Category="MCPython")
    TArray<FString> ServiceNames;

    TArray<FMCPythonBTNodeInfo> Children;
};

UCLASS()
class UNREALMCPYTHON_API UMCPythonHelper : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    // 모든 에디터에서 열려있는 에셋 반환
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython", CallInEditor)
    static TArray<UObject*> GetAllEditedAssets();

    // (예시) 선택된 블루프린트 노드 반환
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython", CallInEditor)
    static TArray<UObject*> GetSelectedBlueprintNodes();

    // 선택된 블루프린트 노드의 연결 정보 반환
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython", CallInEditor)
    static TArray<FMCPythonBlueprintNodeInfo> GetSelectedBlueprintNodeInfos();

    // ─── Behavior Tree Helpers ──────────────────────────────────────────

    /** Get the full tree structure of a Behavior Tree as JSON string (accesses RootNode via C++) */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString GetBehaviorTreeStructure(UBehaviorTree* BehaviorTree);

    /** Set the Blackboard asset on a Behavior Tree (setter not exposed to Python) */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static bool SetBehaviorTreeBlackboard(UBehaviorTree* BehaviorTree, UBlackboardData* BlackboardData);

    /** Get detailed properties of a specific node by name, returned as JSON string */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString GetBehaviorTreeNodeDetails(UBehaviorTree* BehaviorTree, const FString& NodeName);

    /** Get details of selected nodes in the BT editor as JSON */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString GetSelectedBTNodes();

    /** Build a complete Behavior Tree from a JSON structure */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString BuildBehaviorTree(UBehaviorTree* BehaviorTree, const FString& TreeStructureJson);

    /** List all available BT node classes (composites, tasks, decorators, services) */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString ListBTNodeClasses();

    // ─── Blueprint Graph Helpers ──────────────────────────────────────────

    /** Get the full graph info (all nodes, pins, connections) for a Blueprint graph */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString GetBlueprintGraphInfo(UBlueprint* Blueprint, const FString& GraphName);

    /** List callable functions available in a Blueprint context */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString ListCallableFunctions(UBlueprint* Blueprint, const FString& Filter);

    /** List all variables defined in a Blueprint */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString ListBlueprintVariables(UBlueprint* Blueprint);

    /** Add a single node to a Blueprint graph from JSON description */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString AddBlueprintNode(UBlueprint* Blueprint, const FString& GraphName, const FString& NodeJson);

    /** Connect two pins in a Blueprint graph */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString ConnectBlueprintPins(UBlueprint* Blueprint, const FString& GraphName,
        const FString& SourceNodeName, const FString& SourcePinName,
        const FString& TargetNodeName, const FString& TargetPinName);

    /** Remove a node from a Blueprint graph */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString RemoveBlueprintNode(UBlueprint* Blueprint, const FString& GraphName,
        const FString& NodeName);

    /** Build a Blueprint graph from JSON adjacency list (nodes + connections) */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString BuildBlueprintGraph(UBlueprint* Blueprint, const FString& GraphName,
        const FString& GraphJson);

    /** Compile a Blueprint and return the result */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString CompileBlueprint(UBlueprint* Blueprint);

    /** Set any CDO property including inherited C++ UPROPERTYs (e.g. DefaultPawnClass on GameModeBase BPs).
     *  Uses TFieldIterator with IncludeSuper to bypass the Python set_editor_property limitation. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString SetBlueprintCDOProperty(UBlueprint* Blueprint, const FString& PropertyName, const FString& ValueStr);

    // ─── UMG Widget Blueprint Helpers ─────────────────────────────────────────
    // UE 5.7 Python bindings mark UWidgetTree::RootWidget, AllWidgets, and
    // ConstructWidget as protected, so direct Python access is blocked.
    // These UFUNCTIONs proxy the calls through C++ where the members are accessible.

    /** Get widget tree info (root widget, all widgets) as JSON */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString UmgGetWidgetInfo(UBlueprint* WidgetBP);

    /** Add a widget to the widget tree. ParentName="" means auto-root or root panel. Returns JSON. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString UmgAddWidget(UBlueprint* WidgetBP, const FString& WidgetType, const FString& WidgetName, const FString& ParentName);

    /** Find a widget by name in the widget tree. Returns nullptr if not found. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static UWidget* UmgFindWidget(UBlueprint* WidgetBP, const FString& WidgetName);

    /** Remove a widget from the widget tree. Returns JSON. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString UmgRemoveWidget(UBlueprint* WidgetBP, const FString& WidgetName);

    /** Set bIsVariable on a named widget so Blueprint can access it as a variable. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString UmgSetWidgetIsVariable(UBlueprint* WidgetBP, const FString& WidgetName, bool bIsVariable);

    /** Set CanvasPanelSlot layout (anchors + position/size) in one call.
     *  AnchorMin/Max: 0..1 fractions. OffsetX/Y: pixel offset from anchor. SizeX/Y: pixel size. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString UmgSetSlotLayout(UBlueprint* WidgetBP, const FString& WidgetName,
        float AnchorMinX, float AnchorMinY, float AnchorMaxX, float AnchorMaxY,
        float OffsetX, float OffsetY, float SizeX, float SizeY);

    /** Set font size, text color, and outline size on a TextBlock widget in one call. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString UmgSetTextStyle(UBlueprint* WidgetBP, const FString& WidgetName,
        int32 FontSize, float ColorR, float ColorG, float ColorB, float ColorA,
        int32 OutlineSize);

    /** Get an editor property value from a widget as a JSON string. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString UmgGetWidgetProperty(UBlueprint* WidgetBP, const FString& WidgetName, const FString& PropertyName);

    /** Set an editor property value on a widget from a string. Supports bool, int, float, and string properties. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString UmgSetWidgetProperty(UBlueprint* WidgetBP, const FString& WidgetName, const FString& PropertyName, const FString& Value);

    /** Move a widget under a different panel parent (preserves the widget; cycle-guarded). Returns JSON. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString UmgReparentWidget(UBlueprint* WidgetBP, const FString& WidgetName, const FString& NewParentName);

    /** Wrap a widget in a newly-created panel of WrapperType, taking the widget's place in the tree. Returns JSON. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString UmgWrapWidget(UBlueprint* WidgetBP, const FString& WidgetName, const FString& WrapperType, const FString& WrapperName);

    /** Replace a widget with a new widget of NewType at the same slot (old subtree is discarded). Returns JSON. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString UmgReplaceWidget(UBlueprint* WidgetBP, const FString& WidgetName, const FString& NewType, const FString& NewName);

    /** List the bindable multicast-delegate events on a widget (e.g. OnClicked). Returns JSON. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString UmgListWidgetEvents(UBlueprint* WidgetBP, const FString& WidgetName);

    /** Create a bound event node in the widget BP's event graph for a widget's delegate. Returns JSON. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString UmgBindWidgetEvent(UBlueprint* WidgetBP, const FString& WidgetName, const FString& EventName);

    /** Add a component to a Blueprint's SCS.
     *  ComponentClassPath e.g. "/Script/Engine.CameraComponent"
     *  ParentComponentName: name of the parent SCS node, or "" to attach to root */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString AddComponentToBlueprint(UBlueprint* Blueprint,
        const FString& ComponentClassPath,
        const FString& ComponentName,
        float LocationX, float LocationY, float LocationZ,
        float RotationPitch, float RotationYaw, float RotationRoll,
        const FString& ParentComponentName);

    /** List all SCS components on a Blueprint. Returns JSON array of {name, class, variable_name}. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString ListBlueprintComponents(UBlueprint* Blueprint);

    /** Remove a component by variable name from a Blueprint's SCS.
     *  Promotes children to the removed node's parent (safe remove). */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString RemoveComponentFromBlueprint(UBlueprint* Blueprint, const FString& ComponentName);

    /** Set a property on a component template in a Blueprint's SCS.
     *  ComponentName: the variable name of the component.
     *  PropertyName: the property to set (e.g. "relative_location", "sphere_radius").
     *  Value: string representation (e.g. "(X=0,Y=0,Z=100)" or "50.0"). */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString SetComponentProperty(UBlueprint* Blueprint,
        const FString& ComponentName,
        const FString& PropertyName,
        const FString& Value);

    /** Set the canvas position of a node in a Blueprint graph by node name. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString SetBlueprintNodePosition(UBlueprint* Blueprint,
        const FString& GraphName,
        const FString& NodeName,
        float PosX, float PosY);

    /** Set a pin default on a blueprint node.
     *  For object pins, Value should be an asset path like "/Engine/BasicShapes/Sphere.Sphere".
     *  For numeric/bool pins, Value is the literal string like "3.14" or "true". */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString SetBlueprintNodePinDefault(UBlueprint* Blueprint,
        const FString& GraphName,
        const FString& NodeName,
        const FString& PinName,
        const FString& Value);

    // ─── SkeletalMesh / Skeleton Helpers ──────────────────────────────────────
    // Python does not expose reference-skeleton bone enumeration, and
    // USkeletalMeshSocket::SocketName is read-only via Python reflection.
    // These proxy the calls through C++.

    /** List reference-skeleton bones of a SkeletalMesh as JSON [{name, index, parent}]. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString GetSkeletonBones(USkeletalMesh* Mesh);

    /** Add a socket to a SkeletalMesh on a bone with a relative transform. Returns JSON. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString AddSkeletalMeshSocket(USkeletalMesh* Mesh, const FString& SocketName,
        const FString& BoneName,
        float LocationX, float LocationY, float LocationZ,
        float RotationPitch, float RotationYaw, float RotationRoll);

    /** Remove a named socket from a SkeletalMesh. Returns JSON. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString RemoveSkeletalMeshSocket(USkeletalMesh* Mesh, const FString& SocketName);

    // ─── Response transport (python_call) ─────────────────────────────────────
    // The python_call path used to transport results via print() + a GLog capture
    // device. Because the capture device only ADDS to GLog routing, every response
    // was also echoed into the Output Log / log file — including megabyte base64
    // payloads from vision captures, and get_output_log responses re-echoing
    // themselves into ever-deeper escaping. submit_result hands the JSON straight
    // to the server instead, so responses never touch the log.
    //
    // Thread-safety: a single static slot is sufficient because each request is one
    // game-thread task — the write (last python statement) and the read (right
    // after ExecPythonCommandEx returns) are adjacent within that task, and any
    // re-entrant nested request completes atomically in between, never partially.

    /** Called by generated python_call code to hand the action's JSON result back. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static void SubmitResult(const FString& ResultJson);

    /** C++ side: move the submitted result out (returns false if nothing was submitted). */
    static bool ConsumeSubmittedResult(FString& OutResult);

    /** C++ side: drop any stale submitted result before executing a call. */
    static void ClearSubmittedResult();

    // ─── AnimGraph authoring (editor-only AnimGraph module) ───────────────────────
    // AnimGraph node classes (UAnimGraphNode_*) live in the editor-only AnimGraph
    // module and are not exposed to Python, and UAnimationGraph::Nodes is protected,
    // so these operations need C++. Read-only AnimGraph introspection is already
    // served by GetBlueprintGraphInfo (graph_name="AnimGraph").

    /** Add a Sequence Player node to the AnimGraph, optionally linked to the Output Pose. Returns JSON. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString AddAnimGraphSequencePlayer(UAnimBlueprint* AnimBP, const FString& AnimSequencePath, bool bLinkToOutputPose);

    /** Build an arbitrary state machine in the AnimGraph from a JSON spec
        ({states:[{name,anim?}], entry?, transitions:[{from,to,var?,op?,value?}]}). Returns JSON. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString BuildAnimStateMachine(UAnimBlueprint* AnimBP, const FString& SpecJson);

    // ─── Editor viewport projection ───────────────────────────────────────────────
    // FEditorViewportClient / FSceneView are not exposed to Python, so world<->screen
    // projection against the active level editor viewport needs C++.

    /** Project a world location to active-level-viewport pixel coords. Returns JSON {x,y,visible,viewport_*}. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString WorldToScreen(FVector WorldLocation);

    /** Deproject a viewport pixel to a world location at the given distance along the view ray. Returns JSON. */
    UFUNCTION(BlueprintCallable, Category="Editor|MCPython")
    static FString ScreenToWorld(float ScreenX, float ScreenY, float Distance);
};
