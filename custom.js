/* ============================================
   Network Services - Custom JavaScript
   ============================================ */

'use strict';

// Initialize DataTable with common settings
function initDataTable(selector, extraOptions) {
    var defaultOptions = {
        pageLength: 25,
        lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, 'All']],
        dom: '<"row align-items-center mb-3"<"col-sm-6"l><"col-sm-6 text-end"B>>' +
             '<"row"<"col-12"f>>' +
             '<"row"<"col-12"tr>>' +
             '<"row mt-3 align-items-center"<"col-sm-5"i><"col-sm-7"p>>',
        buttons: [
            {
                extend: 'csvHtml5',
                text: '<i class="fa-solid fa-file-csv me-1"></i> CSV',
                className: 'btn btn-outline-secondary btn-sm',
                exportOptions: { columns: ':visible' }
            },
            {
                extend: 'excelHtml5',
                text: '<i class="fa-solid fa-file-excel me-1"></i> Excel',
                className: 'btn btn-outline-success btn-sm',
                exportOptions: { columns: ':visible' }
            },
            {
                extend: 'print',
                text: '<i class="fa-solid fa-print me-1"></i> Print',
                className: 'btn btn-outline-primary btn-sm',
                exportOptions: { columns: ':visible' }
            }
        ],
        responsive: false,
        language: {
            search: '',
            searchPlaceholder: 'Search records...',
            lengthMenu: 'Show _MENU_ entries',
            info: 'Showing _START_ to _END_ of _TOTAL_ records',
            emptyTable: 'No data available',
            zeroRecords: 'No matching records found'
        },
        order: [],
        columnDefs: [
            { targets: 0, width: '50px' }
        ]
    };

    var options = $.extend(true, defaultOptions, extraOptions || {});
    var dt = $(selector).DataTable(options);

    // DataTables genera el input de búsqueda sin id/name, lo que dispara una advertencia
    // de accesibilidad en Chrome. Se parchea inmediatamente tras DataTable() (síncrono)
    // para que el DOM ya tenga los atributos cuando el navegador inspeccione la página.
    var tableId = $(selector).attr('id') || 'dataTable';
    var $searchInput = (
        $('#' + tableId + '_filter input[type="search"]').length
            ? $('#' + tableId + '_filter input[type="search"]')
            : $('.dt-search input[type="search"]').first()
    );
    if ($searchInput.length && !$searchInput.attr('id')) {
        $searchInput.attr({ id: tableId + '-search', name: tableId + '-search' });
    }

    return dt;
}


$(document).ready(function () {

    // ---- Sidebar Toggle ----
    $('#sidebarToggle').on('click', function () {
        if ($(window).width() <= 768) {
            $('#sidebar').toggleClass('mobile-open');
        } else {
            $('#sidebar').toggleClass('collapsed');
            $('#main-content').toggleClass('expanded');
        }
    });

    // Close mobile sidebar on outside click
    $(document).on('click', function (e) {
        if ($(window).width() <= 768) {
            if (!$(e.target).closest('#sidebar, #sidebarToggle').length) {
                $('#sidebar').removeClass('mobile-open');
            }
        }
    });

    // ---- Live Clock ----
    function updateClock() {
        var now = new Date();
        var options = {
            weekday: 'short',
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        };
        var timeStr = now.toLocaleDateString('en-US', options);
        $('#current-time').text(timeStr);
    }

    updateClock();
    setInterval(updateClock, 1000);

    // ---- Tooltips ----
    var tooltipEls = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipEls.forEach(function (el) {
        new bootstrap.Tooltip(el);
    });

    // ---- Auto-dismiss alerts after 5s ----
    setTimeout(function () {
        $('.alert-dismissible').fadeOut('slow');
    }, 5000);

});
